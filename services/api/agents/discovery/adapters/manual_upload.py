"""Manual upload adapter.

User-triggered (not pollable). Exposes two helpers the ``/rfp/upload``
and ``/rfp/ingest`` endpoints use to build ``RawIngestionRecord``
objects that then flow through the normalizer + deduper + upsert path
like any other source.
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pypdf

from ....models.rfp import RawIngestionRecord


ADAPTER_TYPE = "manual_upload"


def build_record_from_pdf(
    file_bytes: bytes,
    filename: str,
    *,
    content_type: Optional[str] = None,
    title: Optional[str] = None,
    agency: Optional[str] = None,
    naics_codes: Optional[List[str]] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> RawIngestionRecord:
    """Extract text from ``file_bytes`` (a PDF) and wrap as a raw record."""
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if not text:
        raise ValueError("PDF had no extractable text")

    digest = hashlib.sha256(file_bytes).hexdigest()
    meta: Dict[str, Any] = {
        "filename": filename,
        "content_type": content_type,
        "title": title or filename,
        "agency": agency,
        "naics_codes": naics_codes or [],
        "sha256": digest,
    }
    if extra_metadata:
        meta.update(extra_metadata)

    return RawIngestionRecord(
        adapter_name=ADAPTER_TYPE,
        adapter_type=ADAPTER_TYPE,
        source_identifier=f"pdf:{digest[:16]}",
        raw_content=text,
        attachments=[file_bytes],
        attachment_filenames=[filename],
        source_url=None,
        fetched_at=datetime.now(timezone.utc),
        adapter_metadata=meta,
    )


def build_record_from_structured(
    *,
    title: str,
    full_text: str,
    agency: Optional[str] = None,
    naics_codes: Optional[List[str]] = None,
    external_id: Optional[str] = None,
    source_url: Optional[str] = None,
    due_date: Optional[datetime] = None,
    value_estimate_low: Optional[int] = None,
    value_estimate_high: Optional[int] = None,
    dedupe_hash: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> RawIngestionRecord:
    """For callers that already have structured RFP fields (``/rfp/ingest``
    JSON body). Wraps them in a raw record so they go through normalize +
    dedupe like every other path — keeps the pipeline single-shaped."""
    seed = dedupe_hash or hashlib.sha256(
        f"{(external_id or '').strip()}|{title.strip()}".encode("utf-8")
    ).hexdigest()
    meta: Dict[str, Any] = {
        "title": title,
        "agency": agency,
        "naics_codes": naics_codes or [],
        "external_id": external_id,
        "source_url": source_url,
        "due_date": due_date.isoformat() if due_date else None,
        "value_estimate_low": value_estimate_low,
        "value_estimate_high": value_estimate_high,
        "dedupe_hash": seed,
    }
    if extra_metadata:
        meta.update(extra_metadata)

    return RawIngestionRecord(
        adapter_name=ADAPTER_TYPE,
        adapter_type=ADAPTER_TYPE,
        source_identifier=f"direct:{seed[:16]}",
        raw_content=full_text,
        source_url=source_url,
        fetched_at=datetime.now(timezone.utc),
        adapter_metadata=meta,
    )
