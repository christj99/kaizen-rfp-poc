from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

# Supplemental Phase 1 amendment (1.A): value set for source_type.
#   'email'         — IMAP adapter
#   'sam_gov'       — SAM.gov public API adapter
#   'manual_upload' — PDF/text upload via UI
#   'url_ingest'    — URL-to-text adapter
RFPSourceType = Literal["email", "sam_gov", "manual_upload", "url_ingest"]

RFPStatus = Literal[
    "new",
    "screened",
    "in_draft",
    "submitted",
    "won",
    "lost",
    "dismissed",
    "needs_manual_review",    # e.g. SAM.gov description fetch failed; awaits manual PDF upload
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RFP(BaseModel):
    """Mirrors the ``rfps`` table. One record per ingested opportunity."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)

    # --- source provenance (supplemental Phase 1 amendment 1.A) ---
    source_type: RFPSourceType
    source_adapter_version: Optional[str] = None
    source_metadata: Dict[str, Any] = Field(default_factory=dict)

    external_id: Optional[str] = None
    title: str
    agency: Optional[str] = None
    naics_codes: List[str] = Field(default_factory=list)
    due_date: Optional[datetime] = None
    value_estimate_low: Optional[int] = None
    value_estimate_high: Optional[int] = None
    full_text: Optional[str] = None
    source_url: Optional[str] = None
    received_at: datetime = Field(default_factory=_utcnow)
    status: RFPStatus = "new"
    dedupe_hash: Optional[str] = None


class RawIngestionRecord(BaseModel):
    """Adapter-level output before normalization to an ``RFP``.

    Each Discovery adapter (email IMAP, SAM.gov, manual upload, URL ingest)
    yields zero or more of these. The normalizer (``services/api/agents/
    discovery/normalizer.py``) is the single choke point that turns them
    into typed ``RFP`` rows, so downstream (screening, drafting, UI) never
    sees source-specific shapes.
    """

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    adapter_name: str                            # instance name, e.g. 'demo_gmail'
    adapter_type: str                            # 'email' | 'sam_gov' | 'manual_upload' | 'url_ingest'
    source_identifier: str                       # unique within the adapter's namespace
    raw_content: str                             # text / HTML / extracted PDF text
    attachments: Optional[List[bytes]] = None    # raw attachment bytes
    attachment_filenames: Optional[List[str]] = None
    source_url: Optional[str] = None
    fetched_at: datetime = Field(default_factory=_utcnow)
    adapter_metadata: Dict[str, Any] = Field(default_factory=dict)
