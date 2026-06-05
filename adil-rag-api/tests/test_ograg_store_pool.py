"""Unit tests for ograg.store's shared connection pool.

Regression coverage for the "sorry, too many clients already" incident: the
retrieval path (one connection per query AND per 5-min probe) must use a single
bounded, memoized pool instead of opening a fresh asyncpg connection every time.

Pure unit tests — no real Postgres. ``asyncpg.create_pool`` is patched so we can
assert pool reuse, bounded sizing, and acquire/release wiring.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import ograg.store as store_mod
import pytest
from ograg.store import Store

pytestmark = pytest.mark.asyncio


def _make_fake_pool() -> MagicMock:
    pool = MagicMock(name="pool")
    pool.acquire = AsyncMock(return_value=MagicMock(name="conn"))
    pool.release = AsyncMock()
    pool.close = AsyncMock()
    return pool


@pytest.fixture(autouse=True)
def _reset_pool_state(monkeypatch):
    """Each test starts with no global pool and a fresh create_pool spy."""
    monkeypatch.setattr(store_mod, "_pool", None, raising=False)
    monkeypatch.setattr(store_mod, "_pool_dsn", None, raising=False)
    yield
    # Leave globals clean for the next test module.
    store_mod._pool = None
    store_mod._pool_dsn = None


async def test_get_pool_is_memoized_per_dsn(monkeypatch):
    fake_pool = _make_fake_pool()
    create = AsyncMock(return_value=fake_pool)
    monkeypatch.setattr(store_mod.asyncpg, "create_pool", create)

    p1 = await store_mod.get_pool("postgres://fake/db")
    p2 = await store_mod.get_pool("postgres://fake/db")

    assert p1 is p2 is fake_pool
    create.assert_awaited_once()  # second call reused the cached pool


async def test_get_pool_is_bounded_with_init_hook(monkeypatch):
    fake_pool = _make_fake_pool()
    create = AsyncMock(return_value=fake_pool)
    monkeypatch.setattr(store_mod.asyncpg, "create_pool", create)

    await store_mod.get_pool("postgres://fake/db")

    _args, kwargs = create.call_args
    assert kwargs["max_size"] == store_mod._POOL_MAX
    assert kwargs["max_size"] >= 1
    # The vector codec + ivfflat.probes must be applied per physical connection.
    assert kwargs["init"] is store_mod._init_connection


async def test_changing_dsn_retires_old_pool(monkeypatch):
    first = _make_fake_pool()
    second = _make_fake_pool()
    create = AsyncMock(side_effect=[first, second])
    monkeypatch.setattr(store_mod.asyncpg, "create_pool", create)

    await store_mod.get_pool("postgres://fake/one")
    await store_mod.get_pool("postgres://fake/two")

    first.close.assert_awaited_once()  # old pool closed before swap
    assert create.await_count == 2


async def test_store_acquires_and_releases_pooled_connection(monkeypatch):
    fake_pool = _make_fake_pool()
    create = AsyncMock(return_value=fake_pool)
    monkeypatch.setattr(store_mod.asyncpg, "create_pool", create)

    s = Store()
    await s.connect("postgres://fake/db")
    conn = await fake_pool.acquire()  # the same MagicMock conn the store holds
    assert s._require_conn() is conn
    fake_pool.acquire.assert_awaited()

    await s.close()
    # Connection returned to the pool — NOT hard-closed.
    fake_pool.release.assert_awaited_once_with(conn)
    assert s._conn is None


async def test_two_stores_share_one_pool(monkeypatch):
    fake_pool = _make_fake_pool()
    create = AsyncMock(return_value=fake_pool)
    monkeypatch.setattr(store_mod.asyncpg, "create_pool", create)

    a, b = Store(), Store()
    await a.connect("postgres://fake/db")
    await b.connect("postgres://fake/db")

    # One pool, created once, shared by both stores → bounded total connections.
    create.assert_awaited_once()
    assert a._pool is b._pool is fake_pool

    await a.close()
    await b.close()


async def test_close_pool_resets_global_state(monkeypatch):
    fake_pool = _make_fake_pool()
    create = AsyncMock(return_value=fake_pool)
    monkeypatch.setattr(store_mod.asyncpg, "create_pool", create)

    await store_mod.get_pool("postgres://fake/db")
    await store_mod.close_pool()

    fake_pool.close.assert_awaited_once()
    assert store_mod._pool is None
    assert store_mod._pool_dsn is None
