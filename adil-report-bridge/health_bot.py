"""
health_bot.py — canonical Telegram health helper for the 13-project portfolio.

Two-tier sends, INDEPENDENT failure paths:
  1. Project-local Telegram chat (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)        ALWAYS
  2. MSentry central inbox (MSENTRY_FEEDBACK_URL + MSENTRY_FEEDBACK_SECRET)     OPTIONAL

Tier 2 is OPTIONAL. To offboard a project from MSentry, unset its env vars and
optionally delete the `# === MSentry block ===` section. The project's own bot
keeps working untouched. The skill's `offboard` mode does this surgically.

Public API:
    notify(severity, kind, message, **context)   # main; never blocks, never raises
    notify_error(service, exc, endpoint=None)    # shortcut for caught exceptions
    notify_health(name, ok, latency_ms=None)     # shortcut for liveness probes
    anotify(...)                                 # async variant for FastAPI/asyncio

Severity vocab (enforced — anything else logs warning + drops):
    info | warn | error | critical

Invariants this module is contractually required to hold (see conformance_test.py):
    1.  Never raises — `notify()` returns None even if everything's broken.
    2.  No-op when env unset — silent for local dev.
    3.  Truncates `message` to 3800 chars before sending (Telegram caps at 4096).
    4.  Markdown attempted; falls back to plain text on Telegram parse error.
    5.  Dedup: identical (severity, kind, message) within 10 min sent once.
    6.  Rate cap: max 30 messages/min per process.
    7.  `disable_web_page_preview: true` by default.
    8.  Project-local TG send and MSentry POST are INDEPENDENT — failure of one never affects the other.
    9.  Severity ∉ {info, warn, error, critical} → drop + warn.
    10. Calling code never waits — both sends fire on a background thread.

Drop into any Python project. Requires only `httpx`.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Final

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # graceful: notify() becomes a no-op


_log = logging.getLogger("health_bot")

VALID_SEVERITIES: Final[tuple[str, ...]] = ("info", "warn", "error", "critical")
SEVERITY_EMOJI: Final[dict[str, str]] = {
    "info": "ℹ️",
    "warn": "⚠️",
    "error": "❌",
    "critical": "🟥",
}
_MAX_LEN: Final[int] = 3800  # Telegram cap is 4096; keep headroom for prefix
_DEDUP_WINDOW_SECS: Final[int] = 600  # 10 min — Bot4 askAdil's pattern
_RATE_LIMIT_PER_MIN: Final[int] = 30  # Bot6 mcb_sre's pattern
_TIMEOUT_SECS: Final[float] = float(os.environ.get("HEALTH_BOT_TIMEOUT_SECS", "8"))


# ── Internal state (per-process) ────────────────────────────────────────────
_dedup_lock = threading.Lock()
_dedup_seen: dict[str, float] = {}  # fingerprint → last_send_epoch
_rate_window: deque[float] = deque()  # epochs of recent sends


def _config_project_tg() -> tuple[str, str] | None:
    """Project-local bot — primary chat for project owner."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    cid = os.environ.get("TELEGRAM_CHAT_ID", "")
    return (tok, cid) if tok and cid else None


def _config_msentry() -> tuple[str, str, str] | None:
    """Central MSentry inbox — optional. Unset to offboard."""
    url = os.environ.get("MSENTRY_FEEDBACK_URL", "")
    secret = os.environ.get("MSENTRY_FEEDBACK_SECRET", "")
    proj = os.environ.get("MSENTRY_PROJECT") or Path.cwd().name
    return (url, secret, proj) if url and secret else None


def _fingerprint(severity: str, kind: str, message: str) -> str:
    return hashlib.sha256(f"{severity}|{kind}|{message}".encode()).hexdigest()


def _should_send(fp: str) -> bool:
    """Combined dedup (10 min) + rate cap (30/min)."""
    now = time.time()
    with _dedup_lock:
        # Rate cap
        while _rate_window and now - _rate_window[0] > 60:
            _rate_window.popleft()
        if len(_rate_window) >= _RATE_LIMIT_PER_MIN:
            return False
        # Dedup
        last = _dedup_seen.get(fp)
        if last and (now - last) < _DEDUP_WINDOW_SECS:
            return False
        _dedup_seen[fp] = now
        _rate_window.append(now)
        # Reap dedup entries that aged out, opportunistically
        if len(_dedup_seen) > 1000:
            cutoff = now - _DEDUP_WINDOW_SECS
            for k in [k for k, t in _dedup_seen.items() if t < cutoff]:
                _dedup_seen.pop(k, None)
        return True


def _format_message(severity: str, kind: str, message: str, context: dict[str, Any]) -> str:
    emoji = SEVERITY_EMOJI.get(severity, "📢")
    lines = [f"{emoji} *{severity.upper()}* `{kind}`", message]
    if context:
        for k, v in list(context.items())[:8]:  # cap context lines
            if v is None:
                continue
            lines.append(f"  • _{k}_: `{v}`")
    return "\n".join(lines)[:_MAX_LEN]


# ── Tier 1: project-local Telegram chat ─────────────────────────────────────
def _send_project_telegram(text: str) -> None:
    cfg = _config_project_tg()
    if not cfg or httpx is None:
        return
    token, chat_id = cfg
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        with httpx.Client(timeout=_TIMEOUT_SECS) as c:
            r = c.post(url, json=body)
        # Markdown parse error → retry with fresh body, no parse_mode (Bot12 turath's pattern)
        if r.status_code != 200 and "can't parse" in r.text.lower():
            plain = {k: v for k, v in body.items() if k != "parse_mode"}
            with httpx.Client(timeout=_TIMEOUT_SECS) as c:
                c.post(url, json=plain)
    except Exception as e:
        _log.warning("project Telegram send failed: %s", e)


# === MSentry block ═════════════════════════════════════════════════════════
# OPTIONAL central inbox. Safe to delete this entire block to offboard from MSentry —
# the project-local bot above keeps working untouched. The skill's `offboard` mode
# does this surgically. ─────────────────────────────────────────────────────
def _send_msentry(severity: str, kind: str, message: str, context: dict[str, Any]) -> None:
    cfg = _config_msentry()
    if not cfg or httpx is None:
        return
    url, secret, project = cfg
    payload = {
        "secret": secret,
        "project": project,
        "severity": severity,
        "kind": kind,
        "message": message[:_MAX_LEN],
        "context": context or {},
    }
    try:
        with httpx.Client(timeout=_TIMEOUT_SECS) as c:
            c.post(url, json=payload)
    except Exception as e:
        _log.warning("msentry feedback failed: %s", e)


# === end MSentry block ═════════════════════════════════════════════════════


def _dispatch(severity: str, kind: str, message: str, context: dict[str, Any]) -> None:
    """Run on a background thread — both sends in parallel, independent failures."""
    text = _format_message(severity, kind, message, context)
    t1 = threading.Thread(target=_send_project_telegram, args=(text,), daemon=True)
    t2 = threading.Thread(target=_send_msentry, args=(severity, kind, message, context), daemon=True)
    t1.start()
    t2.start()


# ── Public API ──────────────────────────────────────────────────────────────
def notify(severity: str, kind: str, message: str, **context: Any) -> None:
    """Fire-and-forget. Never blocks. Never raises.

    Args:
        severity: info | warn | error | critical
        kind:     short tag — e.g. 'deploy', 'health', 'alert', 'metric', 'custom'
        message:  human-readable summary; truncated to 3800 chars
        context:  arbitrary structured data (dict-flat, ≤8 lines surfaced)
    """
    if severity not in VALID_SEVERITIES:
        _log.warning("invalid severity %r — drop. Valid: %s", severity, VALID_SEVERITIES)
        return
    clean_ctx = {k: v for k, v in context.items() if v is not None}
    fp = _fingerprint(severity, kind, str(message))
    if not _should_send(fp):
        return
    threading.Thread(target=_dispatch, args=(severity, kind, str(message), clean_ctx), daemon=True).start()


def notify_error(service: str, exc: BaseException, endpoint: str | None = None) -> None:
    """Catch-and-report shortcut. Use inside `except` blocks."""
    ctx: dict[str, Any] = {"service": service, "exc_type": type(exc).__name__}
    if endpoint:
        ctx["endpoint"] = endpoint
    notify("error", "alert", f"{type(exc).__name__}: {exc}"[:1200], **ctx)


def notify_health(name: str, ok: bool, latency_ms: int | None = None) -> None:
    """Liveness ping. Only fires on transitions or after threshold breaches."""
    if ok:
        if latency_ms is not None and latency_ms > 5000:
            notify("warn", "health", f"{name} slow: {latency_ms}ms")
        # Healthy + fast → silent (the dedup window handles re-sends)
        return
    notify("critical", "health", f"{name} unhealthy", latency_ms=latency_ms if latency_ms is not None else "n/a")


# ── Async variant for FastAPI / asyncio projects ────────────────────────────
async def anotify(severity: str, kind: str, message: str, **context: Any) -> None:
    """Async no-wait variant. Schedules the same background dispatch."""
    notify(severity, kind, message, **context)
