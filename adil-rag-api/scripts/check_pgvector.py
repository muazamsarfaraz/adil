"""Check pgvector availability on the configured DATABASE_URL.

Run via: railway run --service adil-rag-api -- python scripts/check_pgvector.py
"""

import asyncio
import os

import asyncpg


async def main() -> None:
    url = os.environ["DATABASE_URL"]
    print(f"connecting to {url.split('@')[-1].split('/')[0]}...")
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            "SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name LIKE '%vector%'"
        )
        for r in rows:
            print(f"  {r['name']:20s} default={r['default_version']}  installed={r['installed_version']}")
        if not rows:
            print("  NO vector extension available — Railway Postgres image lacks pgvector.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
