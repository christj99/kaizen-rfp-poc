"""Concrete adapter implementations.

Pollable:
  * :mod:`.email_imap` — IMAP/SSL inbox polling
  * :mod:`.sam_gov`    — SAM.gov public search API

One-shot (user-triggered, no scheduler):
  * :mod:`.manual_upload` — PDF / structured-field ingestion helpers
  * :mod:`.url_ingest`    — URL-fetch ingestion helper
"""

from .email_imap import EmailIMAPAdapter
from .manual_upload import build_record_from_pdf, build_record_from_structured
from .sam_gov import SAMGovAdapter
from .url_ingest import build_record_from_url

__all__ = [
    "EmailIMAPAdapter",
    "SAMGovAdapter",
    "build_record_from_pdf",
    "build_record_from_structured",
    "build_record_from_url",
]
