from pydantic import BaseModel, Field


class SettingsRead(BaseModel):
    listen_ip: str
    listen_port: int
    log_max_entries: int

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    listen_ip: str | None = None
    listen_port: int | None = Field(default=None, ge=1, le=65535)
    log_max_entries: int | None = Field(default=None, ge=10, le=100000)
