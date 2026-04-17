import aiosqlite
from app.config import get_settings

settings = get_settings()

CREATE_MAPPINGS_TABLE = """
CREATE TABLE IF NOT EXISTS mappings (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    input_pattern TEXT NOT NULL,
    input_type  TEXT NOT NULL DEFAULT 'exact_hex',
    output_type TEXT NOT NULL,
    output_config TEXT NOT NULL DEFAULT '{}',
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

CREATE_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS app_settings (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    listen_ip       TEXT NOT NULL DEFAULT '0.0.0.0',
    listen_port     INTEGER NOT NULL DEFAULT 5005,
    log_max_entries INTEGER NOT NULL DEFAULT 1000
);
"""

INSERT_DEFAULT_SETTINGS = """
INSERT OR IGNORE INTO app_settings (id, listen_ip, listen_port, log_max_entries)
VALUES (1, ?, ?, ?);
"""


def get_db() -> aiosqlite.Connection:
    """Return an aiosqlite connection context manager."""
    return aiosqlite.connect(settings.database_url)


async def init_db() -> None:
    import os
    os.makedirs(os.path.dirname(settings.database_url), exist_ok=True)

    async with aiosqlite.connect(settings.database_url) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(CREATE_MAPPINGS_TABLE)
        await db.execute(CREATE_SETTINGS_TABLE)
        await db.execute(
            INSERT_DEFAULT_SETTINGS,
            (settings.udp_listen_ip, settings.udp_listen_port, settings.log_max_entries),
        )
        await db.commit()
