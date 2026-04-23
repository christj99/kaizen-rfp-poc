"""SAM.gov public-search adapter.

Migrated from the Phase 2 single-file ``agents/discovery.py``. Key shape
change: ``fetch()`` yields :class:`RawIngestionRecord` rather than full
``RFP`` objects, so the normalizer is the single translation layer.

SAM.gov's ``description`` endpoint is known flaky (see
``docs/sam_gov_issues.md``); failures per record are captured in
``adapter_metadata['description_fetch_status']`` so the normalizer can
flag the RFP as ``status='needs_manual_review'`` without the adapter
having to know about RFP status.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional

import httpx

from .... import _env  # noqa: F401 — populates os.environ from .env
from ....config.loader import SamGovAdapterConfig
from ...discovery.base import AdapterBase, HealthStatus
from ....models.rfp import RawIngestionRecord

log = logging.getLogger(__name__)

SAM_GOV_API_URL = "https://api.sam.gov/opportunities/v2/search"
_DEFAULT_LOOKBACK_DAYS = 30
_DEFAULT_HTTP_TIMEOUT = 30.0


class SAMGovAdapter(AdapterBase):
    adapter_type = "sam_gov"

    def __init__(
        self,
        cfg: SamGovAdapterConfig,
        *,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
        limit: int = 50,
        keyword: Optional[str] = None,
        fetch_full_text: Optional[bool] = None,
        http_client: Optional[httpx.Client] = None,
    ):
        self.name = cfg.name
        self.cfg = cfg
        self.lookback_days = lookback_days
        self.limit = limit
        self.keyword = keyword
        self.fetch_full_text = (
            fetch_full_text
            if fetch_full_text is not None
            else cfg.fallback_strategy.try_description_endpoint
        )
        self._http = http_client

    # -- AdapterBase ---------------------------------------------------

    def fetch(self) -> Iterator[RawIngestionRecord]:
        key = self._api_key()
        if not self.cfg.naics_filter:
            log.warning("SAMGovAdapter %s has no naics_filter; returning nothing", self.name)
            return

        close_client = self._http is None
        client = self._http or httpx.Client(timeout=_DEFAULT_HTTP_TIMEOUT)
        try:
            now = datetime.now(timezone.utc)
            since = now - timedelta(days=self.lookback_days)
            params: Dict[str, Any] = {
                "api_key": key,
                "limit": min(self.limit, 1000),
                "postedFrom": since.strftime("%m/%d/%Y"),
                "postedTo": now.strftime("%m/%d/%Y"),
                "ncode": ",".join(self.cfg.naics_filter),
            }
            if self.keyword:
                params["q"] = self.keyword

            resp = client.get(SAM_GOV_API_URL, params=params)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"SAM.gov returned {resp.status_code}: {resp.text[:300]}"
                )
            payload = resp.json()
            records = payload.get("opportunitiesData") or []
            log.info(
                "SAM.gov %s returned %d records (total %s)",
                self.name, len(records), payload.get("totalRecords"),
            )

            for raw in records:
                yield self._record_to_raw(raw, client, key)
        finally:
            if close_client:
                client.close()

    def health_check(self) -> HealthStatus:
        try:
            key = self._api_key()
        except Exception as exc:
            return HealthStatus(status="down", detail=str(exc))
        # We could ping /opportunities/v2/search?limit=1 but that burns quota.
        # A key-present check is sufficient at rest; callers hit fetch() for liveness.
        return HealthStatus(
            status="ok",
            detail="key present; description endpoint is known flaky (see docs/sam_gov_issues.md)",
            metadata={"naics_filter": self.cfg.naics_filter},
        )

    # -- internals -----------------------------------------------------

    def _api_key(self) -> str:
        key = os.environ.get(self.cfg.api_key_env, "").strip()
        if not key:
            raise RuntimeError(
                f"{self.cfg.api_key_env} not set — get a key at https://sam.gov/content/api-keys"
            )
        return key

    def _record_to_raw(
        self, raw: Dict[str, Any], client: httpx.Client, api_key: str
    ) -> RawIngestionRecord:
        title = raw.get("title") or raw.get("noticeId") or "(untitled)"
        notice_id = raw.get("noticeId") or raw.get("solicitationNumber") or ""
        ui_link = raw.get("uiLink")

        description_text, desc_status = "", "skipped"
        if self.fetch_full_text:
            description_text, desc_status = self._fetch_description(raw, client, api_key)

        # Build dedupe hash (stable across re-polls).
        dedupe_seed = f"{(raw.get('solicitationNumber') or '').strip()}|{title.strip()}"
        dedupe_hash = hashlib.sha256(dedupe_seed.encode("utf-8")).hexdigest()

        # raw_content: prefer the full description; fall back to title for dedupe reconstructibility.
        raw_content = description_text.strip() or title

        return RawIngestionRecord(
            adapter_name=self.name,
            adapter_type=self.adapter_type,
            source_identifier=notice_id or dedupe_hash,
            raw_content=raw_content,
            source_url=ui_link,
            fetched_at=datetime.now(timezone.utc),
            adapter_metadata={
                "raw_record": raw,
                "description_fetch_status": desc_status,
                "dedupe_hash": dedupe_hash,
                "fallback_on_failure": self.cfg.fallback_strategy.on_description_failure,
            },
        )

    def _fetch_description(
        self, record: Dict[str, Any], client: httpx.Client, api_key: str
    ) -> tuple[str, str]:
        """Returns ``(text, status)``. ``status`` is ``ok``/``http_<code>``/``exception``."""
        url = record.get("description")
        if not isinstance(url, str) or not url.startswith("http"):
            return "", "missing_url"

        backoff = 1.0
        last_status = "unknown"
        for attempt in range(1, 4):
            try:
                resp = client.get(url, params={"api_key": api_key})
                if resp.status_code == 200:
                    data = resp.json() if resp.text else {}
                    text = (data.get("description") or "").strip() if isinstance(data, dict) else ""
                    return text, "ok"
                last_status = f"http_{resp.status_code}"
                if resp.status_code >= 500 and attempt < 3:
                    import time
                    time.sleep(backoff); backoff *= 2
                    continue
                return "", last_status
            except (httpx.HTTPError, ValueError) as exc:
                last_status = f"exception:{type(exc).__name__}"
                if attempt < 3:
                    import time
                    time.sleep(backoff); backoff *= 2
                    continue
                return "", last_status
        return "", last_status
