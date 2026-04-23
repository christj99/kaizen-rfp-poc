"""Discovery agent — SAM.gov ingestion.

Pulls opportunity records via SAM.gov's public Get-Opportunities API,
normalizes each into an ``RFP`` row, and dedupes against records already
in the database.

Docs: https://open.gsa.gov/api/get-opportunities-public-api/
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from .. import _env  # noqa: F401 — populates os.environ from .env
from ..db.client import upsert_rfp
from ..models.rfp import RFP

log = logging.getLogger(__name__)

SAM_GOV_API_URL = "https://api.sam.gov/opportunities/v2/search"
_DEFAULT_LOOKBACK_DAYS = 30
_DEFAULT_HTTP_TIMEOUT = 30.0


class DiscoveryError(RuntimeError):
    pass


def fetch_sam_gov_rfps(
    naics_codes: List[str],
    *,
    modified_since: Optional[datetime] = None,
    limit: int = 50,
    api_key: Optional[str] = None,
    fetch_full_text: bool = True,
    persist: bool = True,
    http_client: Optional[httpx.Client] = None,
) -> List[RFP]:
    """Fetch opportunities matching the given NAICS codes.

    Parameters
    ----------
    naics_codes:
        One or more NAICS codes to filter by. An empty list returns nothing
        (SAM.gov's search requires at least one ``ncode`` to be useful).
    modified_since:
        Posted-from date. Defaults to 30 days ago.
    limit:
        Max records to return. SAM.gov caps at 1000 per call.
    fetch_full_text:
        When True (default), fetches the description URL for each record and
        stores it in ``full_text``. Costs one extra HTTP request per record.
    persist:
        When True (default), upserts each record via the DB client; records
        already present (by dedupe_hash) are skipped silently.

    Returns
    -------
    list[RFP]
        The newly-ingested RFPs (not the pre-existing ones, when ``persist``
        is True).
    """
    if not naics_codes:
        return []

    key = api_key or os.environ.get("SAM_GOV_API_KEY")
    if not key:
        raise DiscoveryError(
            "SAM_GOV_API_KEY not set — get a free key at https://sam.gov/content/api-keys."
        )

    modified_since = modified_since or (
        datetime.now(timezone.utc) - timedelta(days=_DEFAULT_LOOKBACK_DAYS)
    )
    posted_from = modified_since.strftime("%m/%d/%Y")
    posted_to = datetime.now(timezone.utc).strftime("%m/%d/%Y")

    params: Dict[str, Any] = {
        "api_key": key,
        "limit": min(limit, 1000),
        "postedFrom": posted_from,
        "postedTo": posted_to,
        "ncode": ",".join(naics_codes),
    }

    close_client = http_client is None
    client = http_client or httpx.Client(timeout=_DEFAULT_HTTP_TIMEOUT)
    try:
        resp = client.get(SAM_GOV_API_URL, params=params)
        if resp.status_code != 200:
            raise DiscoveryError(
                f"SAM.gov API returned {resp.status_code}: {resp.text[:500]}"
            )
        payload = resp.json()
        records = payload.get("opportunitiesData") or []
        log.info(
            "SAM.gov returned %d records (total %s) for NAICS %s",
            len(records),
            payload.get("totalRecords"),
            naics_codes,
        )

        rfps: List[RFP] = []
        for raw in records:
            rfp = _record_to_rfp(raw)
            if rfp is None:
                continue
            if fetch_full_text and rfp.source_url:
                rfp.full_text = _fetch_description(client, raw, key)
            rfps.append(rfp)

        if not persist:
            return rfps

        persisted: List[RFP] = []
        for rfp in rfps:
            before = rfp.id
            stored = upsert_rfp(rfp)
            # upsert_rfp returns the existing row when dedupe_hash matches —
            # caller wants only records that are truly new.
            if stored.id == before:
                persisted.append(stored)
        return persisted
    finally:
        if close_client:
            client.close()


# -- normalization -----------------------------------------------------

def _record_to_rfp(record: Dict[str, Any]) -> Optional[RFP]:
    title = record.get("title") or record.get("noticeId")
    if not title:
        return None

    external_id = record.get("solicitationNumber") or record.get("noticeId")
    agency = record.get("fullParentPathName")
    naics = record.get("naicsCode")
    naics_codes = [naics] if isinstance(naics, str) and naics else []

    due_date = _parse_datetime(record.get("responseDeadLine"))

    award = record.get("award") or {}
    value_low, value_high = _parse_award(award)

    source_url = record.get("uiLink") or record.get("description")

    dedupe_hash = _dedupe_hash(external_id, title)

    return RFP(
        source="sam_gov",
        external_id=external_id,
        title=title,
        agency=agency,
        naics_codes=naics_codes,
        due_date=due_date,
        value_estimate_low=value_low,
        value_estimate_high=value_high,
        full_text=None,  # populated lazily by fetch_full_text
        source_url=source_url,
        dedupe_hash=dedupe_hash,
    )


def _dedupe_hash(solicitation_number: Optional[str], title: str) -> str:
    raw = f"{(solicitation_number or '').strip()}|{title.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    # SAM.gov uses ISO 8601 with offset (e.g. 2024-04-15T17:00:00-04:00).
    # Python's fromisoformat handles that as of 3.11.
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _parse_award(award: Dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
    amount = award.get("amount")
    if amount is None:
        return (None, None)
    try:
        n = int(float(amount))
        return (n, n)
    except (TypeError, ValueError):
        return (None, None)


def _fetch_description(
    client: httpx.Client, record: Dict[str, Any], api_key: str
) -> Optional[str]:
    """Pull the opportunity's narrative description.

    SAM.gov stores the long-form description at a separate URL; the record's
    ``description`` field is a URL that returns ``{"description": "..."}``.
    Failures are non-fatal — we fall back to the short-form data we already
    have.
    """
    url = record.get("description")
    if not isinstance(url, str) or not url.startswith("http"):
        return None
    try:
        resp = client.get(url, params={"api_key": api_key})
        if resp.status_code != 200:
            log.warning(
                "description fetch for %s returned %s",
                record.get("noticeId"),
                resp.status_code,
            )
            return None
        data = resp.json()
        text = data.get("description") if isinstance(data, dict) else None
        if isinstance(text, str):
            return text.strip()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("description fetch failed for %s: %s", record.get("noticeId"), exc)
    return None
