from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class JobTriggerResponse(BaseModel):
    job_type: str
    status: str
    message: str
    molecule_id: UUID | None = None
