"""IMAP email ingestion adapter.

Pollable adapter that logs into a mailbox over IMAPS, reads unseen
messages, and yields one :class:`RawIngestionRecord` per message with:

* ``raw_content``     = ``Subject:`` line + text/html body + extracted PDF text
* ``adapter_metadata`` = ``from``, ``to``, ``date``, ``subject``, attachment names
* ``source_identifier`` = the IMAP UID (stable within a mailbox)

PDF attachments are text-extracted via ``pypdf`` so Screening has full
content to reason over. Failures on a single attachment are logged but
don't sink the whole message — email signatures and random PNGs arrive
as attachments all the time.

The IMAP connection is opened per fetch and closed cleanly — long-lived
IMAP connections fail in subtle ways (Gmail in particular will reset
them). The ``mark_as_read`` flag in config controls whether processed
messages transition to SEEN on the server.
"""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from imap_tools import AND, MailBox

import pypdf

from .... import _env  # noqa: F401
from ....config.loader import EmailAdapterConfig
from ...discovery.base import AdapterBase, HealthStatus
from ....models.rfp import RawIngestionRecord

log = logging.getLogger(__name__)


class EmailIMAPAdapter(AdapterBase):
    adapter_type = "email"

    def __init__(self, cfg: EmailAdapterConfig):
        self.name = cfg.name
        self.cfg = cfg

    # -- AdapterBase ---------------------------------------------------

    def fetch(self) -> Iterator[RawIngestionRecord]:
        user, pw = self._credentials()
        with MailBox(self.cfg.host, port=self.cfg.port).login(
            user, pw, initial_folder=self.cfg.folder
        ) as mb:
            # bulk=False keeps memory usage down on large inboxes.
            for msg in mb.fetch(
                AND(seen=False),
                mark_seen=self.cfg.mark_as_read,
                bulk=False,
            ):
                try:
                    yield self._build_record(msg)
                except Exception:
                    log.exception("Failed to build record from message uid=%s", getattr(msg, "uid", "?"))

    def health_check(self) -> HealthStatus:
        try:
            user, pw = self._credentials()
        except Exception as exc:
            return HealthStatus(status="down", detail=str(exc))
        try:
            with MailBox(self.cfg.host, port=self.cfg.port).login(
                user, pw, initial_folder=self.cfg.folder
            ) as mb:
                total = len(list(mb.uids("ALL")))
                unread = len(list(mb.uids("UNSEEN")))
                return HealthStatus(
                    status="ok",
                    detail=f"{user}@{self.cfg.host}/{self.cfg.folder}",
                    metadata={"total": total, "unread": unread},
                )
        except Exception as exc:
            return HealthStatus(status="down", detail=f"{type(exc).__name__}: {exc}")

    # -- internals -----------------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        user = os.environ.get(self.cfg.username_env, "").strip()
        pw = os.environ.get(self.cfg.password_env, "").strip().replace(" ", "")
        if not user or not pw:
            raise RuntimeError(
                f"IMAP credentials missing: set {self.cfg.username_env} and "
                f"{self.cfg.password_env} in .env (Gmail app passwords are 16 chars; "
                f"see README 'Demo email setup')."
            )
        return user, pw

    def _build_record(self, msg) -> RawIngestionRecord:
        subject = msg.subject or "(no subject)"
        body_parts: List[str] = [f"Subject: {subject}", ""]

        if self.cfg.parse_strategy.text_body:
            body = (msg.text or "").strip() or (msg.html or "").strip()
            if body:
                body_parts.append(body)

        attachments_payloads: List[bytes] = []
        attachment_filenames: List[str] = []

        if self.cfg.parse_strategy.pdf_attachments:
            for att in msg.attachments or []:
                filename = att.filename or "(unnamed)"
                attachment_filenames.append(filename)
                attachments_payloads.append(att.payload)
                if not filename.lower().endswith(".pdf"):
                    continue
                try:
                    reader = pypdf.PdfReader(io.BytesIO(att.payload))
                    pdf_text = "\n\n".join(
                        (page.extract_text() or "") for page in reader.pages
                    ).strip()
                    if pdf_text:
                        body_parts.append("")
                        body_parts.append(f"--- Attachment: {filename} ---")
                        body_parts.append(pdf_text)
                except Exception as exc:
                    # Noisy signature images, corrupt PDFs, etc. — log and continue.
                    log.warning(
                        "PDF extract failed for %s (msg uid %s): %s",
                        filename, getattr(msg, "uid", "?"), exc,
                    )

        return RawIngestionRecord(
            adapter_name=self.name,
            adapter_type=self.adapter_type,
            source_identifier=str(msg.uid),
            raw_content="\n".join(body_parts).strip(),
            attachments=attachments_payloads or None,
            attachment_filenames=attachment_filenames or None,
            source_url=None,
            fetched_at=datetime.now(timezone.utc),
            adapter_metadata={
                "from": msg.from_,
                "to": list(msg.to) if msg.to else [],
                "subject": subject,
                "date": msg.date.isoformat() if msg.date else None,
                "attachment_count": len(attachment_filenames),
                "folder": self.cfg.folder,
            },
        )
