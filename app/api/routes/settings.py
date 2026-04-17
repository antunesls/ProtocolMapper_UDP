from fastapi import APIRouter

from app.api.schemas.settings import SettingsRead, SettingsUpdate
from app.core.udp_server import udp_server
from app.db import repository as repo

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/", response_model=SettingsRead)
async def get_settings():
    return await repo.get_settings_record()


@router.put("/", response_model=SettingsRead)
async def update_settings(body: SettingsUpdate):
    current = await repo.get_settings_record()
    updated = await repo.update_settings_record(body.model_dump(exclude_none=True))

    # Restart UDP server if network settings changed
    if (
        updated["listen_ip"] != current["listen_ip"]
        or updated["listen_port"] != current["listen_port"]
    ):
        await udp_server.restart(updated["listen_ip"], updated["listen_port"])

    return updated
