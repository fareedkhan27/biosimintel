from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthCheck(BaseModel):
    status: str
    version: str
    dependencies: dict[str, Any]
