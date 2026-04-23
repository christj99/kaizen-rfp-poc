"""Coordinate adapters -> normalizer -> deduper -> RFP store.

Supplemental plan Amendment 2.H. One-shot and scheduled both land here:

* ``run_discovery()``            — iterate every enabled pollable adapter
* ``run_adapter(name)``          — run a specific adapter by name
* ``build_all_adapters()``       — factory for the orchestrator + Settings UI
* ``ingest_raw_record(record)``  — shared tail (normalize + dedupe + upsert),
                                    used by the manual/url ingest endpoints
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...config.loader import AppConfig, get_config
from ...db.client import write_audit
from ...models.audit import AuditEntry
from ...models.rfp import RFP, RawIngestionRecord
from .adapters.email_imap import EmailIMAPAdapter
from .adapters.sam_gov import SAMGovAdapter
from .base import AdapterBase, HealthStatus
from .deduper import dedupe_and_upsert
from .normalizer import normalize

log = logging.getLogger(__name__)


@dataclass
class AdapterRunResult:
    adapter_name: str
    adapter_type: str
    new_rfps: List[RFP] = field(default_factory=list)
    duplicates: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DiscoveryRunResult:
    adapters_run: List[AdapterRunResult] = field(default_factory=list)

    @property
    def total_new(self) -> int:
        return sum(len(a.new_rfps) for a in self.adapters_run)

    @property
    def total_duplicates(self) -> int:
        return sum(a.duplicates for a in self.adapters_run)

    @property
    def total_errors(self) -> int:
        return sum(len(a.errors) for a in self.adapters_run)


# -- adapter factory --------------------------------------------------

def build_all_adapters(cfg: Optional[AppConfig] = None) -> List[AdapterBase]:
    """Every pollable adapter for every enabled source family."""
    cfg = cfg or get_config()
    adapters: List[AdapterBase] = []
    if cfg.sources.email.enabled:
        for ac in cfg.sources.email.adapters:
            adapters.append(EmailIMAPAdapter(ac))
    if cfg.sources.sam_gov.enabled:
        for ac in cfg.sources.sam_gov.adapters:
            adapters.append(SAMGovAdapter(ac))
    return adapters


def build_adapter_by_name(name: str, cfg: Optional[AppConfig] = None) -> Optional[AdapterBase]:
    for a in build_all_adapters(cfg):
        if a.name == name:
            return a
    return None


def adapter_health_snapshot() -> List[Dict[str, Any]]:
    """Health status for every configured adapter — feeds the Settings UI."""
    out: List[Dict[str, Any]] = []
    for a in build_all_adapters():
        try:
            h: HealthStatus = a.health_check()
            out.append({
                "name": a.name,
                "adapter_type": a.adapter_type,
                "status": h.status,
                "detail": h.detail,
                "metadata": h.metadata,
            })
        except Exception as exc:
            out.append({
                "name": a.name,
                "adapter_type": a.adapter_type,
                "status": "down",
                "detail": f"{type(exc).__name__}: {exc}",
                "metadata": {},
            })
    return out


# -- run ---------------------------------------------------------------

def ingest_raw_record(record: RawIngestionRecord) -> tuple[RFP, bool]:
    """Shared tail: normalize + dedupe + upsert. Returns (rfp, was_new)."""
    rfp = normalize(record)
    stored, was_new = dedupe_and_upsert(rfp)

    # Single audit line per ingestion; the screening path writes its own.
    try:
        write_audit(
            AuditEntry(
                entity_type="rfp",
                entity_id=stored.id,
                action="discovery_ingest" if was_new else "discovery_duplicate",
                actor="system",
                details={
                    "adapter_name": record.adapter_name,
                    "adapter_type": record.adapter_type,
                    "source_identifier": record.source_identifier,
                    "was_new": was_new,
                    "title": stored.title,
                    "status": stored.status,
                },
            )
        )
    except Exception:
        log.exception("audit write failed for ingestion of %s", record.source_identifier)

    return stored, was_new


def run_adapter(adapter: AdapterBase) -> AdapterRunResult:
    """Drain a single adapter's fetch() and pipe records through the pipeline."""
    result = AdapterRunResult(adapter_name=adapter.name, adapter_type=adapter.adapter_type)
    try:
        for record in adapter.fetch():
            try:
                stored, was_new = ingest_raw_record(record)
                if was_new:
                    result.new_rfps.append(stored)
                else:
                    result.duplicates += 1
            except Exception as exc:
                log.exception("normalize/upsert failed for %s", record.source_identifier)
                result.errors.append({
                    "record": record.source_identifier,
                    "error": f"{type(exc).__name__}: {exc}",
                })
    except Exception as exc:
        log.exception("adapter %s fetch() failed", adapter.name)
        result.errors.append({
            "fatal": True,
            "error": f"{type(exc).__name__}: {exc}",
        })
    return result


def run_discovery(adapter_names: Optional[List[str]] = None) -> DiscoveryRunResult:
    """Run every enabled adapter (or the named subset). Returns per-adapter results."""
    cfg = get_config()
    adapters = build_all_adapters(cfg)
    if adapter_names:
        adapters = [a for a in adapters if a.name in adapter_names]

    summary = DiscoveryRunResult()
    for adapter in adapters:
        summary.adapters_run.append(run_adapter(adapter))
    return summary
