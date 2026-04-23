"""URL-fetch adapter.

One-shot: the user hands us a URL (SAM.gov workspace page, agency
portal, etc.), we fetch it, extract text, and produce a
:class:`RawIngestionRecord`.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from ....models.rfp import RawIngestionRecord


ADAPTER_TYPE = "url_ingest"
_USER_AGENT = "Mozilla/5.0 (compatible; kaizen-rfp-poc/0.1; +https://github.com/)"
_HTTP_TIMEOUT = 30.0


def build_record_from_url(
    url: str,
    *,
    title: Optional[str] = None,
    agency: Optional[str] = None,
    naics_codes: Optional[List[str]] = None,
    http_client: Optional[httpx.Client] = None,
) -> RawIngestionRecord:
    """Fetch ``url``, strip to text, wrap as a raw record.

    Caller can override ``title``/``agency`` if the page doesn't yield
    clean values.
    """
    close_client = http_client is None
    client = http_client or httpx.Client(
        timeout=_HTTP_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
    )
    try:
        resp = client.get(url)
        resp.raise_for_status()
        body = resp.text
    finally:
        if close_client:
            client.close()

    soup = BeautifulSoup(body, "html.parser")
    # Strip noise.
    for tag in soup(("script", "style", "noscript", "header", "footer", "nav")):
        tag.decompose()

    page_title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    text = " ".join(soup.get_text(separator=" ").split()).strip()

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    meta: Dict[str, Any] = {
        "url": url,
        "page_title": page_title,
        "title": title or page_title or url,
        "agency": agency,
        "naics_codes": naics_codes or [],
    }

    return RawIngestionRecord(
        adapter_name=ADAPTER_TYPE,
        adapter_type=ADAPTER_TYPE,
        source_identifier=f"url:{digest[:16]}",
        raw_content=text,
        source_url=url,
        fetched_at=datetime.now(timezone.utc),
        adapter_metadata=meta,
    )
