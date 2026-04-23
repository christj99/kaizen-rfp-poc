"""Turn :class:`RawIngestionRecord` into a typed :class:`RFP`.

Single choke point: every ingestion path — email, SAM.gov, manual
upload, URL ingest — flows through here. Downstream (screening,
drafting, UI) never sees adapter-specific shapes.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dateutil import parser as dtparser  # type: ignore[import-untyped]

from ...models.rfp import RFP, RawIngestionRecord

log = logging.getLogger(__name__)


# ---------- public API -----------------------------------------------

def normalize(record: RawIngestionRecord) -> RFP:
    adapter_type = record.adapter_type
    if adapter_type == "email":
        return _normalize_email(record)
    if adapter_type == "sam_gov":
        return _normalize_sam_gov(record)
    if adapter_type == "manual_upload":
        return _normalize_manual_upload(record)
    if adapter_type == "url_ingest":
        return _normalize_url_ingest(record)
    raise ValueError(f"Unknown adapter_type: {adapter_type!r}")


# ---------- email ----------------------------------------------------

_NAICS_RE = re.compile(r"\b(\d{6})\b")
_DEADLINE_KEYWORDS = re.compile(
    r"(?:response\s+due|due\s+date|proposal\s+due|submission\s+deadline|response\s+deadline|closing\s+date|deadline)\s*[:\-]?\s*(.{0,60})",
    re.IGNORECASE,
)


def _normalize_email(record: RawIngestionRecord) -> RFP:
    meta = record.adapter_metadata or {}
    subject = meta.get("subject") or "(no subject)"
    body = record.raw_content or ""

    dedupe = hashlib.sha256(
        f"email|{record.adapter_name}|{record.source_identifier}".encode("utf-8")
    ).hexdigest()

    from_addr = meta.get("from") or ""
    agency = _agency_from_sender(from_addr)
    naics = _extract_naics(body)
    due_date = _extract_due_date(body)

    return RFP(
        source_type="email",
        source_adapter_version="email_v1",
        source_metadata={
            "from": from_addr,
            "to": meta.get("to") or [],
            "subject": subject,
            "received_at": meta.get("date"),
            "attachment_filenames": record.attachment_filenames or [],
            "adapter_name": record.adapter_name,
            "imap_uid": record.source_identifier,
        },
        external_id=None,
        title=subject,
        agency=agency,
        naics_codes=naics,
        due_date=due_date,
        full_text=body,
        source_url=None,
        dedupe_hash=dedupe,
    )


def _agency_from_sender(from_addr: str) -> Optional[str]:
    # e.g. "John Doe <john.doe@gsa.gov>" -> "gsa.gov"
    m = re.search(r"<([^@]+)@([^>]+)>", from_addr or "")
    if m:
        return m.group(2).strip()
    m = re.search(r"@([A-Za-z0-9.\-]+)", from_addr or "")
    if m:
        return m.group(1).strip()
    return None


def _extract_naics(text: str) -> List[str]:
    if not text:
        return []
    # NAICS codes are 6 digits. Grab up to 3 unique codes from the text.
    codes = []
    for m in _NAICS_RE.finditer(text):
        code = m.group(1)
        if code not in codes:
            codes.append(code)
        if len(codes) >= 3:
            break
    return codes


def _extract_due_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    m = _DEADLINE_KEYWORDS.search(text)
    if not m:
        return None
    snippet = m.group(1)
    try:
        parsed = dtparser.parse(snippet, fuzzy=True, default=datetime(1970, 1, 1, tzinfo=timezone.utc))
    except (dtparser.ParserError, ValueError, OverflowError):
        return None
    # Fuzzy parsing on junk can return 1970; reject those.
    if parsed.year < 2000:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ---------- SAM.gov --------------------------------------------------

def _normalize_sam_gov(record: RawIngestionRecord) -> RFP:
    meta = record.adapter_metadata or {}
    raw = meta.get("raw_record") or {}
    desc_status = meta.get("description_fetch_status", "unknown")

    title = raw.get("title") or raw.get("noticeId") or "(untitled)"
    external_id = raw.get("solicitationNumber") or raw.get("noticeId")
    agency = raw.get("fullParentPathName")
    naics_codes: List[str] = []
    if isinstance(raw.get("naicsCode"), str) and raw["naicsCode"]:
        naics_codes = [raw["naicsCode"]]

    due_date = _parse_iso_datetime(raw.get("responseDeadLine"))
    value_low, value_high = _parse_award_amount(raw.get("award"))

    # If the description endpoint failed, flag the RFP so the UI's Needs Attention
    # queue picks it up (supplemental plan Amendment 5.C).
    fallback = meta.get("fallback_on_failure") or "flag_for_manual_review"
    status: Any = "new"
    if desc_status not in ("ok", "skipped") and fallback == "flag_for_manual_review":
        status = "needs_manual_review"

    return RFP(
        source_type="sam_gov",
        source_adapter_version="sam_gov_v1",
        source_metadata={
            "notice_id": raw.get("noticeId"),
            "notice_type": raw.get("type"),
            "set_aside": raw.get("typeOfSetAsideDescription"),
            "posted_date": raw.get("postedDate"),
            "active": raw.get("active"),
            "description_fetch_status": desc_status,
            "adapter_name": record.adapter_name,
        },
        external_id=external_id,
        title=title,
        agency=agency,
        naics_codes=naics_codes,
        due_date=due_date,
        value_estimate_low=value_low,
        value_estimate_high=value_high,
        full_text=record.raw_content or None,
        source_url=record.source_url,
        status=status,
        dedupe_hash=meta.get("dedupe_hash") or hashlib.sha256(
            f"sam_gov|{external_id or ''}|{title}".encode("utf-8")
        ).hexdigest(),
    )


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _parse_award_amount(award: Any) -> tuple[Optional[int], Optional[int]]:
    if not isinstance(award, dict):
        return (None, None)
    amount = award.get("amount")
    if amount is None:
        return (None, None)
    try:
        n = int(float(amount))
        return (n, n)
    except (TypeError, ValueError):
        return (None, None)


# ---------- manual_upload -------------------------------------------

def _normalize_manual_upload(record: RawIngestionRecord) -> RFP:
    meta = record.adapter_metadata or {}
    title = meta.get("title") or "Manual upload"
    dedupe = meta.get("dedupe_hash") or hashlib.sha256(
        f"manual|{record.source_identifier}|{title}".encode("utf-8")
    ).hexdigest()
    due = meta.get("due_date")
    due_dt = _parse_iso_datetime(due) if isinstance(due, str) else (due if isinstance(due, datetime) else None)

    return RFP(
        source_type="manual_upload",
        source_adapter_version="manual_upload_v1",
        source_metadata={
            "filename": meta.get("filename"),
            "content_type": meta.get("content_type"),
            "sha256": meta.get("sha256"),
            "adapter_name": record.adapter_name,
        },
        external_id=meta.get("external_id"),
        title=title,
        agency=meta.get("agency"),
        naics_codes=list(meta.get("naics_codes") or []),
        due_date=due_dt,
        value_estimate_low=meta.get("value_estimate_low"),
        value_estimate_high=meta.get("value_estimate_high"),
        full_text=record.raw_content or None,
        source_url=meta.get("source_url") or record.source_url,
        dedupe_hash=dedupe,
    )


# ---------- url_ingest ----------------------------------------------

def _normalize_url_ingest(record: RawIngestionRecord) -> RFP:
    meta = record.adapter_metadata or {}
    title = meta.get("title") or meta.get("page_title") or meta.get("url") or "URL ingest"
    url = meta.get("url") or record.source_url
    dedupe = hashlib.sha256(f"url|{url}".encode("utf-8")).hexdigest()

    body = record.raw_content or ""
    naics = list(meta.get("naics_codes") or []) or _extract_naics(body)
    due_date = _extract_due_date(body)

    return RFP(
        source_type="url_ingest",
        source_adapter_version="url_ingest_v1",
        source_metadata={
            "url": url,
            "page_title": meta.get("page_title"),
            "adapter_name": record.adapter_name,
        },
        external_id=None,
        title=title,
        agency=meta.get("agency"),
        naics_codes=naics,
        due_date=due_date,
        full_text=body or None,
        source_url=url,
        dedupe_hash=dedupe,
    )
