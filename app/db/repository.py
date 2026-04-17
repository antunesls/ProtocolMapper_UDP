import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.db.database import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_mapping(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    d["output_config"] = json.loads(d["output_config"])
    d["enabled"] = bool(d["enabled"])
    return d


def _row_to_settings(row: aiosqlite.Row) -> dict[str, Any]:
    return dict(row)


# ---------------------------------------------------------------------------
# Mapping CRUD
# ---------------------------------------------------------------------------

async def list_mappings(enabled_only: bool = False) -> list[dict[str, Any]]:
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        if enabled_only:
            cursor = await db.execute(
                "SELECT * FROM mappings WHERE enabled = 1 ORDER BY created_at"
            )
        else:
            cursor = await db.execute("SELECT * FROM mappings ORDER BY created_at")
        rows = await cursor.fetchall()
    return [_row_to_mapping(r) for r in rows]


async def get_mapping(mapping_id: str) -> dict[str, Any] | None:
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM mappings WHERE id = ?", (mapping_id,))
        row = await cursor.fetchone()
    return _row_to_mapping(row) if row else None


async def create_mapping(data: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    mapping_id = str(uuid.uuid4())
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO mappings (id, name, input_pattern, input_type, output_type,
                                  output_config, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mapping_id,
                data["name"],
                data["input_pattern"],
                data.get("input_type", "exact_hex"),
                data["output_type"],
                json.dumps(data.get("output_config", {})),
                int(data.get("enabled", True)),
                now,
                now,
            ),
        )
        await db.commit()
    return await get_mapping(mapping_id)  # type: ignore[return-value]


async def update_mapping(mapping_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    existing = await get_mapping(mapping_id)
    if existing is None:
        return None

    merged = {**existing, **data, "updated_at": _now_iso()}
    async with get_db() as db:
        await db.execute(
            """
            UPDATE mappings
            SET name=?, input_pattern=?, input_type=?, output_type=?,
                output_config=?, enabled=?, updated_at=?
            WHERE id=?
            """,
            (
                merged["name"],
                merged["input_pattern"],
                merged["input_type"],
                merged["output_type"],
                json.dumps(merged["output_config"]),
                int(merged["enabled"]),
                merged["updated_at"],
                mapping_id,
            ),
        )
        await db.commit()
    return await get_mapping(mapping_id)


async def delete_mapping(mapping_id: str) -> bool:
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM mappings WHERE id = ?", (mapping_id,))
        await db.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Settings CRUD
# ---------------------------------------------------------------------------

async def get_settings_record() -> dict[str, Any]:
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM app_settings WHERE id = 1")
        row = await cursor.fetchone()
    return _row_to_settings(row)  # always exists (seeded by init_db)


async def update_settings_record(data: dict[str, Any]) -> dict[str, Any]:
    existing = await get_settings_record()
    merged = {**existing, **data}
    async with get_db() as db:
        await db.execute(
            """
            UPDATE app_settings
            SET listen_ip=?, listen_port=?, log_max_entries=?
            WHERE id=1
            """,
            (merged["listen_ip"], merged["listen_port"], merged["log_max_entries"]),
        )
        await db.commit()
    return await get_settings_record()
