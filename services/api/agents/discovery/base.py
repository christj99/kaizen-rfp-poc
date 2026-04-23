"""Adapter base class + health-check data shape.

Every ingestion adapter inherits ``AdapterBase``. Pollable adapters
(``email``, ``sam_gov``) override ``fetch()`` to yield
:class:`RawIngestionRecord` instances; one-shot paths
(``manual_upload``, ``url_ingest``) leave ``fetch()`` as a no-op and
expose module-level helpers for building a single record from user
action. Every concrete adapter must implement ``health_check()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, Literal

from pydantic import BaseModel, Field

from ...models.rfp import RawIngestionRecord

HealthStatusLevel = Literal["ok", "degraded", "down"]


class HealthStatus(BaseModel):
    """Adapter health snapshot — surfaced in the Settings UI and /discovery/adapters."""

    status: HealthStatusLevel
    detail: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AdapterBase(ABC):
    name: str = ""               # instance name (e.g. 'demo_gmail', 'sam_gov_primary')
    adapter_type: str = ""       # 'email' | 'sam_gov' | 'manual_upload' | 'url_ingest'

    @abstractmethod
    def health_check(self) -> HealthStatus:
        """Return adapter reachability + any operationally useful counters."""

    def fetch(self) -> Iterator[RawIngestionRecord]:
        """Yield raw records. Default empty-iterator is for one-shot adapters."""
        return iter(())
