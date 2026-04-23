"""Reads ``config/config.yaml`` into a pydantic model.

Hot reloadable — the Settings page in the UI calls ``reload_config()`` after it
writes changes back to disk, so flipping ``mode`` or moving a threshold doesn't
require an API restart.
"""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, Field

Mode = Literal["manual", "chain", "full_auto"]


class ScreeningConfig(BaseModel):
    threshold_pursue: int = 75
    threshold_maybe: int = 50


class DraftingConfig(BaseModel):
    auto_draft_threshold: int = 90


class SamGovSourceConfig(BaseModel):
    enabled: bool = True
    naics_filter: List[str] = Field(default_factory=list)
    poll_interval_hours: int = 4


class EmailSourceConfig(BaseModel):
    enabled: bool = False


class ManualUploadSourceConfig(BaseModel):
    enabled: bool = True


class SourcesConfig(BaseModel):
    sam_gov: SamGovSourceConfig = Field(default_factory=SamGovSourceConfig)
    email: EmailSourceConfig = Field(default_factory=EmailSourceConfig)
    manual_upload: ManualUploadSourceConfig = Field(default_factory=ManualUploadSourceConfig)


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


# Repo layout: <repo>/services/api/config/loader.py -> parents[3] = <repo>
DEFAULT_CONFIG_PATH: Path = Path(__file__).resolve().parents[3] / "config" / "config.yaml"

_lock = RLock()
_cached: Optional[AppConfig] = None
_cached_path: Optional[Path] = None


def load_config(path: Optional[Path] = None, *, force_reload: bool = False) -> AppConfig:
    """Return the parsed config, caching the first successful read."""
    global _cached, _cached_path
    target = (path or DEFAULT_CONFIG_PATH).resolve()
    with _lock:
        if not force_reload and _cached is not None and _cached_path == target:
            return _cached
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        _cached = AppConfig.model_validate(raw)
        _cached_path = target
        return _cached


def reload_config(path: Optional[Path] = None) -> AppConfig:
    return load_config(path, force_reload=True)


def get_config() -> AppConfig:
    return load_config()


def save_config(config: AppConfig, path: Optional[Path] = None) -> AppConfig:
    """Persist ``config`` to YAML and refresh the cache.

    The Settings page uses this; writing directly to the file + calling
    ``reload_config`` also works, but this keeps the round trip in one place.
    """
    target = (path or DEFAULT_CONFIG_PATH).resolve()
    target.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return reload_config(target)
