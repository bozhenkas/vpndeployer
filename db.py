import asyncpg
from typing import Optional

_pool: Optional[asyncpg.Pool] = None

DDL = """
CREATE TABLE IF NOT EXISTS deployments (
    id          SERIAL PRIMARY KEY,
    tg_user_id  BIGINT NOT NULL,
    scenario    VARCHAR(10),
    status      VARCHAR(20) DEFAULT 'deploying',
    main_ip     VARCHAR(64),
    sub_url     TEXT,
    vless_links TEXT[],
    error_msg   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);
"""


async def init(dsn: str) -> None:
    global _pool
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    async with _pool.acquire() as conn:
        await conn.execute(DDL)


def pool() -> asyncpg.Pool:
    assert _pool is not None, "db not initialised"
    return _pool


async def create_deployment(tg_user_id: int, scenario: str, main_ip: str) -> int:
    row = await pool().fetchrow(
        "INSERT INTO deployments (tg_user_id, scenario, main_ip) VALUES ($1,$2,$3) RETURNING id",
        tg_user_id, scenario, main_ip,
    )
    return row["id"]


async def finish_deployment(
    dep_id: int,
    *,
    success: bool,
    sub_url: str | None = None,
    vless_links: list[str] | None = None,
    error_msg: str | None = None,
) -> None:
    status = "success" if success else "failed"
    await pool().execute(
        """UPDATE deployments
           SET status=$2, sub_url=$3, vless_links=$4, error_msg=$5, finished_at=NOW()
           WHERE id=$1""",
        dep_id, status, sub_url, vless_links or [], error_msg,
    )


async def get_user_deployments(tg_user_id: int) -> list[asyncpg.Record]:
    return await pool().fetch(
        "SELECT * FROM deployments WHERE tg_user_id=$1 ORDER BY created_at DESC LIMIT 10",
        tg_user_id,
    )
