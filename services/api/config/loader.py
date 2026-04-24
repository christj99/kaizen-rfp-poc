"""Reads ``config/config.yaml`` into a pydantic model.

Hot reloadable — the Settings page in the UI calls ``reload_config()`` after it
writes changes back to disk, so flipping ``mode`` or moving a threshold doesn't
require an API restart.

Supplemental Phase 1 amendment (1.B): ``sources`` is restructured to hold
per-adapter instances so new ingestion paths can be added as config only.
"""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["manual", "chain", "full_auto"]


class ScreeningConfig(BaseModel):
    threshold_pursue: int = 75
    threshold_maybe: int = 50


class DraftingConfig(BaseModel):
    auto_draft_threshold: int = 90


# -- adapter configs --------------------------------------------------
# These mirror the adapter-specific blocks under ``sources.<family>.adapters``.
# ``extra='allow'`` keeps unknown fields accessible via ``__pydantic_extra__``
# so new adapter types can ship without a loader change.

class AdapterConfigBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str                          # instance name, e.g. 'demo_gmail'
    type: str                          # adapter implementation key


class EmailParseStrategy(BaseModel):
    pdf_attachments: bool = True
    text_body: bool = True
    digest_parser: bool = False        # stretch goal


class EmailAdapterConfig(AdapterConfigBase):
    host: str
    port: int = 993
    username_env: str                  # env var name (not the value) so secrets stay out of config
    password_env: str
    folder: str = "INBOX"
    poll_interval_minutes: int = 5
    mark_as_read: bool = True
    parse_strategy: EmailParseStrategy = Field(default_factory=EmailParseStrategy)
    use_llm_extraction: bool = False


class SamGovFallbackStrategy(BaseModel):
    try_description_endpoint: bool = True
    on_description_failure: Literal[
        "flag_for_manual_review", "skip", "retry_later"
    ] = "flag_for_manual_review"


class SamGovAdapterConfig(AdapterConfigBase):
    api_key_env: str = "SAM_GOV_API_KEY"
    naics_filter: List[str] = Field(default_factory=list)
    poll_interval_hours: int = 4
    fallback_strategy: SamGovFallbackStrategy = Field(
        default_factory=SamGovFallbackStrategy
    )


class EmailSourceConfig(BaseModel):
    enabled: bool = False
    primary: bool = False
    adapters: List[EmailAdapterConfig] = Field(default_factory=list)


class SamGovSourceConfig(BaseModel):
    enabled: bool = True
    primary: bool = False
    adapters: List[SamGovAdapterConfig] = Field(default_factory=list)


class PassthroughSourceConfig(BaseModel):
    """manual_upload / url_ingest — no adapter fan-out; a single flag is enough."""
    enabled: bool = True
    primary: bool = False


class SourcesConfig(BaseModel):
    email: EmailSourceConfig = Field(default_factory=EmailSourceConfig)
    sam_gov: SamGovSourceConfig = Field(default_factory=SamGovSourceConfig)
    manual_upload: PassthroughSourceConfig = Field(default_factory=PassthroughSourceConfig)
    url_ingest: PassthroughSourceConfig = Field(default_factory=PassthroughSourceConfig)

    # -- convenience accessors --

    def primary_family(self) -> Optional[str]:
        """Return the family key flagged as primary, or ``None`` if none is."""
        for name in ("email", "sam_gov", "manual_upload", "url_ingest"):
            family = getattr(self, name)
            if getattr(family, "primary", False) and getattr(family, "enabled", False):
                return name
        return None

    def all_adapter_configs(self) -> List[AdapterConfigBase]:
        """Return every enabled adapter across all families, flattened."""
        out: List[AdapterConfigBase] = []
        if self.email.enabled:
            out.extend(self.email.adapters)
        if self.sam_gov.enabled:
            out.extend(self.sam_gov.adapters)
        return out


class SlackConfig(BaseModel):
    enabled: bool = True
    notification_threshold: int = 75


class LLMConfig(BaseModel):
    model: str = "claude-sonnet-4-5"
    max_tokens: int = 4096
    temperature: float = 0.3


class AppConfig(BaseModel):
    mode: Mode = "manual"
    screening: ScreeningConfig = Field(default_factory=ScreeningConfig)
    drafting: DraftingConfig = Field(default_factory=DraftingConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)


DEFAULT_CONFIG_PATH: Path = Path(__file__).resolve().parents[3] / "config" / "config.yaml"

_lock = RLock()
_cached: Optional[AppConfig] = None
_cached_path: Optional[Path] = None
_cached_mtime: Optional[float] = None


def load_config(path: Optional[Path] = None, *, force_reload: bool = False) -> AppConfig:
    """Return the parsed config, caching the first successful read.

    Auto-reloads when the source file's mtime changes since the last
    successful parse — so `config.mode` edits take effect on the next
    ``get_config()`` call without an API restart. The Settings page can
    still call ``reload_config()`` explicitly for belt-and-suspenders.
    """
    global _cached, _cached_path, _cached_mtime
    target = (path or DEFAULT_CONFIG_PATH).resolve()
    try:
        current_mtime = target.stat().st_mtime
    except OSError:
        current_mtime = None

    with _lock:
        cache_valid = (
            not force_reload
            and _cached is not None
            and _cached_path == target
            and _cached_mtime == current_mtime
        )
        if cache_valid:
            return _cached  # type: ignore[return-value]

        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        _cached = AppConfig.model_validate(raw)
        _cached_path = target
        _cached_mtime = current_mtime
        return _cached


def reload_config(path: Optional[Path] = None) -> AppConfig:
    return load_config(path, force_reload=True)


def get_config() -> AppConfig:
    return load_config()


def save_config(config: AppConfig, path: Optional[Path] = None) -> AppConfig:
    target = (path or DEFAULT_CONFIG_PATH).resolve()
    target.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return reload_config(target)
