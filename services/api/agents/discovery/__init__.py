"""Discovery package — multi-source ingestion (supplemental Phase 2 amendment).

High-level entry points:

* :func:`run_discovery` / :func:`run_adapter` / :func:`ingest_raw_record`
  — orchestrator.py
* :func:`normalize` — normalizer.py
* :class:`AdapterBase` / :class:`HealthStatus` — base.py
* :class:`EmailIMAPAdapter`, :class:`SAMGovAdapter`,
  :func:`build_record_from_pdf`, :func:`build_record_from_structured`,
  :func:`build_record_from_url` — adapters/*
"""

from .adapters import (
    EmailIMAPAdapter,
    SAMGovAdapter,
    build_record_from_pdf,
    build_record_from_structured,
    build_record_from_url,
)
from .base import AdapterBase, HealthStatus
from .deduper import dedupe_and_upsert
from .normalizer import normalize
from .orchestrator import (
    AdapterRunResult,
    DiscoveryRunResult,
    adapter_health_snapshot,
    build_adapter_by_name,
    build_all_adapters,
    ingest_raw_record,
    run_adapter,
    run_discovery,
)

__all__ = [
    "AdapterBase",
    "AdapterRunResult",
    "DiscoveryRunResult",
    "EmailIMAPAdapter",
    "HealthStatus",
    "SAMGovAdapter",
    "adapter_health_snapshot",
    "build_adapter_by_name",
    "build_all_adapters",
    "build_record_from_pdf",
    "build_record_from_structured",
    "build_record_from_url",
    "dedupe_and_upsert",
    "ingest_raw_record",
    "normalize",
    "run_adapter",
    "run_discovery",
]
