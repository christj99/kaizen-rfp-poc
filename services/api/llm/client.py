"""Claude API wrapper.

One entrypoint — ``LLMClient.call_claude`` — used by every agent. Centralizing
here keeps retries, JSON parsing, mock mode, and audit logging in one place so
individual agents don't re-implement them.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional, Tuple

import anthropic
from anthropic import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from .. import _env  # noqa: F401 — populates os.environ from .env
from ..config.loader import get_config
from ..db.client import write_audit
from ..models.audit import AuditEntry

log = logging.getLogger(__name__)

MOCK_ENV_VAR = "LLM_MOCK_MODE"
_TRANSIENT_ERRORS: Tuple[type, ...] = (
    RateLimitError,
    InternalServerError,
    APIConnectionError,
    APITimeoutError,
)


class LLMError(Exception):
    """Raised when Claude can't be called or returns invalid output after retries."""


class LLMClient:
    """Thin wrapper around ``anthropic.Anthropic``.

    Parameters
    ----------
    model:
        Override the ``llm.model`` from config.yaml. Useful for per-agent pins
        (e.g. a cheaper model for chat, Opus for drafting).
    mock_mode:
        When True, ``call_claude`` returns a canned response without hitting
        the network. Also enabled by ``LLM_MOCK_MODE=1`` in the environment.
    api_key:
        Override the ``ANTHROPIC_API_KEY`` env var. Handy for tests.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        mock_mode: Optional[bool] = None,
        api_key: Optional[str] = None,
    ):
        self._llm_cfg = get_config().llm
        self._model = model or self._llm_cfg.model

        env_mock = os.environ.get(MOCK_ENV_VAR, "0") == "1"
        self._mock_mode = env_mock if mock_mode is None else mock_mode

        if self._mock_mode:
            self._client: Optional[anthropic.Anthropic] = None
        else:
            resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not resolved_key:
                raise LLMError(
                    "ANTHROPIC_API_KEY not set — populate .env or pass api_key=."
                )
            self._client = anthropic.Anthropic(api_key=resolved_key)

    # -- public ---------------------------------------------------------

    def call_claude(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        audit_entity_type: Optional[str] = None,
        audit_entity_id: Optional[uuid.UUID] = None,
        audit_action: str = "llm_call",
    ) -> Any:
        """Call Claude with a system + user prompt.

        If ``response_schema`` is provided, the wrapper nudges the model toward
        JSON, parses it, and returns a dict. Otherwise it returns the raw
        string.

        On rate-limit or transient server errors, retries with exponential
        backoff. On a JSON parse failure (only when ``response_schema`` is set),
        retries once at ``temperature=0`` with a stricter reminder before
        giving up.
        """
        resolved_model = model or self._model
        resolved_max = max_tokens or self._llm_cfg.max_tokens
        resolved_temp = (
            temperature if temperature is not None else self._llm_cfg.temperature
        )

        if self._mock_mode:
            return self._mock_response(response_schema)

        effective_system = self._apply_schema_instruction(
            system_prompt, response_schema
        )

        text, usage = self._call_with_retries(
            model=resolved_model,
            system=effective_system,
            user_prompt=user_prompt,
            max_tokens=resolved_max,
            temperature=resolved_temp,
        )

        self._audit(
            action=audit_action,
            entity_type=audit_entity_type,
            entity_id=audit_entity_id,
            details={
                "model": resolved_model,
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "schema_enforced": bool(response_schema),
            },
        )

        if response_schema is None:
            return text

        return self._parse_json(
            text,
            schema=response_schema,
            model=resolved_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=resolved_max,
        )

    # -- internals ------------------------------------------------------

    @staticmethod
    def _apply_schema_instruction(
        system_prompt: str, schema: Optional[Dict[str, Any]]
    ) -> str:
        if not schema:
            return system_prompt
        return (
            f"{system_prompt}\n\n"
            "---\n"
            "Respond with a SINGLE JSON object that matches the schema below.\n"
            "No prose before or after. No markdown code fences. Just the object.\n\n"
            f"JSON schema:\n{json.dumps(schema, indent=2)}"
        )

    def _call_with_retries(
        self,
        *,
        model: str,
        system: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        max_retries: int = 4,
    ) -> Tuple[str, Dict[str, Optional[int]]]:
        assert self._client is not None, "LLMClient in mock mode has no Anthropic client"

        backoff = 1.0
        last_exc: Optional[BaseException] = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                text = "".join(
                    block.text
                    for block in resp.content
                    if getattr(block, "type", None) == "text"
                )
                usage = {
                    "input_tokens": getattr(resp.usage, "input_tokens", None),
                    "output_tokens": getattr(resp.usage, "output_tokens", None),
                }
                return text, usage
            except _TRANSIENT_ERRORS as exc:
                last_exc = exc
                log.warning(
                    "Claude transient error (%s/%s): %s — sleeping %.1fs",
                    attempt,
                    max_retries,
                    type(exc).__name__,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= 2
        raise LLMError(
            f"Claude call failed after {max_retries} retries: {last_exc!r}"
        )

    def _parse_json(
        self,
        text: str,
        *,
        schema: Dict[str, Any],
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> Dict[str, Any]:
        cleaned = self._strip_code_fence(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            log.warning("Claude returned non-JSON; retrying with stricter prompt")

        strict_system = (
            f"{system_prompt}\n\n"
            "---\n"
            "Your previous response was not valid JSON. Return ONLY the JSON "
            "object — no code fences, no commentary, no leading/trailing text.\n\n"
            f"JSON schema:\n{json.dumps(schema, indent=2)}"
        )
        retry_text, _ = self._call_with_retries(
            model=model,
            system=strict_system,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=0.0,
        )
        try:
            return json.loads(self._strip_code_fence(retry_text))
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Claude returned non-JSON response twice. Last output:\n{retry_text[:500]}"
            ) from exc

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        s = text.strip()
        if s.startswith("```"):
            # Strip the opening fence (``` or ```json) and the closing fence.
            s = s.lstrip("`").lstrip()
            if s.lower().startswith("json"):
                s = s[4:].lstrip()
            if s.endswith("```"):
                s = s[:-3].rstrip()
        return s

    @staticmethod
    def _mock_response(schema: Optional[Dict[str, Any]]) -> Any:
        if schema is None:
            return "[mock] LLM_MOCK_MODE is on — no network call was made."
        return {"mock": True, "note": "LLM_MOCK_MODE is on"}

    @staticmethod
    def _audit(
        *,
        action: str,
        entity_type: Optional[str],
        entity_id: Optional[uuid.UUID],
        details: Dict[str, Any],
    ) -> None:
        try:
            write_audit(
                AuditEntry(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    action=action,
                    actor="claude",
                    details=details,
                )
            )
        except Exception:
            # Audit writes must never break the primary call path.
            log.exception("Failed to write audit entry for LLM call")
