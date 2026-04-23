"""Environment loading helper.

Wraps ``dotenv.load_dotenv`` to solve one specific footgun: on some shells
(particularly PowerShell with user profile exports) an env var may be set
to the empty string. The default ``load_dotenv`` refuses to overwrite it,
so ``ANTHROPIC_API_KEY=""`` in the shell wins over ``ANTHROPIC_API_KEY=sk-...``
in ``.env`` — which manifests as a confusing "key not set" error later.

Rule we want:
  * shell has real value   → shell wins (don't override)
  * shell has empty string → treat as unset, let .env populate
  * shell has nothing      → .env populates
"""

from __future__ import annotations

import os
from typing import Iterable

from dotenv import load_dotenv

# Keys whose empty-string shell values should defer to .env.
_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "SAM_GOV_API_KEY",
    "SLACK_WEBHOOK_URL",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "N8N_BASIC_AUTH_USER",
    "N8N_BASIC_AUTH_PASSWORD",
    "N8N_HOST",
    "N8N_PORT",
    "API_HOST",
    "API_PORT",
    "STREAMLIT_PORT",
    "LLM_MOCK_MODE",
)


def load_env(keys: Iterable[str] = _ENV_KEYS) -> None:
    """Populate env vars from ``.env``, clearing shell-exported empties first."""
    for key in keys:
        if key in os.environ and os.environ[key].strip() == "":
            os.environ.pop(key, None)
    load_dotenv()


load_env()
