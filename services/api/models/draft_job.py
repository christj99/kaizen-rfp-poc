"""DraftJob — async drafting job state (Phase 3B).

The job row is the durable record of an async draft request. The actual
work runs in a FastAPI ``BackgroundTasks`` callable; this model is just
the shape clients poll for ``/draft/job/{id}``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

DraftJobStatus = Literal["queued", "running", "completed", "failed"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DraftJob(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)
    rfp_id: UUID
    status: DraftJobStatus = "queued"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    draft_id: Optional[UUID] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
