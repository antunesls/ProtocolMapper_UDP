from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator


class InputType(str, Enum):
    exact_hex = "exact_hex"
    exact_text = "exact_text"
    regex = "regex"


class OutputType(str, Enum):
    http = "http"
    udp = "udp"
    tcp = "tcp"
    mqtt = "mqtt"
    ui24r = "ui24r"
    sequence = "sequence"
    ramp = "ramp"


class MappingBase(BaseModel):
    name: str
    input_pattern: str
    input_type: InputType = InputType.exact_hex
    output_type: OutputType
    output_config: dict[str, Any] = {}
    enabled: bool = True


class MappingCreate(MappingBase):
    pass


class MappingUpdate(BaseModel):
    name: str | None = None
    input_pattern: str | None = None
    input_type: InputType | None = None
    output_type: OutputType | None = None
    output_config: dict[str, Any] | None = None
    enabled: bool | None = None


class MappingRead(MappingBase):
    id: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
