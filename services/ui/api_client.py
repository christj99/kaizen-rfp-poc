"""Thin HTTP client to the FastAPI service.

Streamlit re-runs the entire script on every interaction, so all reads are
cached via ``st.cache_data(ttl=10)`` to avoid hammering the API. Writes
(mutations) are never cached.

Centralizing here keeps every page using the same URL + error handling.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
import streamlit as st


def _api_base() -> str:
    return (os.environ.get("KAIZEN_API_URL")
            or f"http://localhost:{os.environ.get('API_PORT', '8000')}").rstrip("/")


class APIError(Exception):
    """Wraps any failure communicating with the API. Raised so pages can
    render a friendly banner instead of crashing on httpx exceptions."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(base_url=_api_base(), timeout=timeout)


def _raise(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise APIError(f"{resp.status_code}: {detail}", status_code=resp.status_code)


# ---------- reads (cached) -------------------------------------------

@st.cache_data(ttl=5, show_spinner=False)
def health() -> Dict[str, Any]:
    with _client(timeout=5.0) as c:
        r = c.get("/health")
        _raise(r)
        return r.json()


@st.cache_data(ttl=10, show_spinner=False)
def list_rfps(
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    with_screening: bool = True,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"with_screening": str(with_screening).lower(), "limit": limit}
    if status: params["status"] = status
    if source_type: params["source_type"] = source_type
    with _client() as c:
        r = c.get("/rfps", params=params)
        _raise(r)
        return r.json()


@st.cache_data(ttl=5, show_spinner=False)
def get_rfp(rfp_id: str) -> Dict[str, Any]:
    with _client() as c:
        r = c.get(f"/rfp/{rfp_id}")
        _raise(r)
        return r.json()


@st.cache_data(ttl=5, show_spinner=False)
def get_similar_proposals(rfp_id: str, k: int = 3) -> List[Dict[str, Any]]:
    with _client() as c:
        r = c.get(f"/rfp/{rfp_id}/similar-proposals", params={"k": k})
        _raise(r)
        return r.json()


@st.cache_data(ttl=10, show_spinner=False)
def list_audit(limit: int = 25) -> List[Dict[str, Any]]:
    with _client() as c:
        r = c.get("/audit_log", params={"limit": limit})
        _raise(r)
        return r.json()


@st.cache_data(ttl=30, show_spinner=False)
def list_past_proposals(search: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"limit": limit}
    if search: params["search"] = search
    with _client() as c:
        r = c.get("/past_proposals", params=params)
        _raise(r)
        return r.json()


@st.cache_data(ttl=30, show_spinner=False)
def get_past_proposal(proposal_id: str) -> Dict[str, Any]:
    with _client() as c:
        r = c.get(f"/past_proposal/{proposal_id}")
        _raise(r)
        return r.json()


@st.cache_data(ttl=5, show_spinner=False)
def get_config() -> Dict[str, Any]:
    with _client() as c:
        r = c.get("/config")
        _raise(r)
        return r.json()


@st.cache_data(ttl=10, show_spinner=False)
def get_rubric() -> Dict[str, Any]:
    with _client() as c:
        r = c.get("/rubric")
        _raise(r)
        return r.json()


@st.cache_data(ttl=10, show_spinner=False)
def list_adapters() -> List[Dict[str, Any]]:
    with _client() as c:
        r = c.get("/discovery/adapters")
        _raise(r)
        return r.json()


# Draft job polling — never cache; status is the whole point.

def get_draft_job(job_id: str) -> Dict[str, Any]:
    with _client(timeout=10.0) as c:
        r = c.get(f"/draft/job/{job_id}")
        _raise(r)
        return r.json()


def get_draft(draft_id: str) -> Dict[str, Any]:
    with _client() as c:
        r = c.get(f"/draft/{draft_id}")
        _raise(r)
        return r.json()


# ---------- writes (no cache) ----------------------------------------

def ingest_rfp(payload: Dict[str, Any]) -> Dict[str, Any]:
    with _client(timeout=60.0) as c:
        r = c.post("/rfp/ingest", json=payload)
        _raise(r)
        return r.json()


def ingest_url(url: str, title: Optional[str] = None, agency: Optional[str] = None) -> Dict[str, Any]:
    with _client(timeout=60.0) as c:
        r = c.post("/rfp/ingest_url", json={"url": url, "title": title, "agency": agency})
        _raise(r)
        return r.json()


def upload_pdf(file_bytes: bytes, filename: str, title: Optional[str] = None, agency: Optional[str] = None) -> Dict[str, Any]:
    with _client(timeout=120.0) as c:
        files = {"file": (filename, file_bytes, "application/pdf")}
        data: Dict[str, Any] = {}
        if title: data["title"] = title
        if agency: data["agency"] = agency
        r = c.post("/rfp/upload", files=files, data=data)
        _raise(r)
        return r.json()


def screen_rfp(rfp_id: str) -> Dict[str, Any]:
    with _client(timeout=300.0) as c:
        r = c.post(f"/rfp/{rfp_id}/screen")
        _raise(r)
        return r.json()


def kickoff_draft(rfp_id: str, mode: str = "async") -> Dict[str, Any]:
    """For async mode returns ``{job_id, status='queued', ...}`` immediately."""
    with _client(timeout=30.0) as c:
        r = c.post(f"/rfp/{rfp_id}/draft", params={"mode": mode})
        _raise(r)
        return r.json()


def override_screening(rfp_id: str, recommendation: str, reason: Optional[str] = None) -> None:
    with _client() as c:
        r = c.post(f"/rfp/{rfp_id}/override", json={"recommendation": recommendation, "reason": reason})
        _raise(r)


def update_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    with _client() as c:
        r = c.put("/config", json=updates)
        _raise(r)
        return r.json()


def update_rubric(rubric: Dict[str, Any]) -> Dict[str, Any]:
    with _client(timeout=30.0) as c:
        r = c.put("/rubric", json={"rubric": rubric})
        _raise(r)
        return r.json()


def run_adapter(adapter_name: str) -> Dict[str, Any]:
    with _client(timeout=120.0) as c:
        r = c.post(f"/discovery/run/{adapter_name}")
        _raise(r)
        return r.json()


def chat(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    with _client(timeout=120.0) as c:
        r = c.post("/chat", json={"messages": messages})
        _raise(r)
        return r.json()


def export_draft_url(draft_id: str) -> str:
    return f"{_api_base()}/draft/{draft_id}/export"


def cache_clear() -> None:
    """Drop all cached reads. Call after a write so the next read is fresh."""
    for fn in (health, list_rfps, get_rfp, get_similar_proposals, list_audit,
               list_past_proposals, get_past_proposal, get_config, get_rubric,
               list_adapters):
        try:
            fn.clear()  # type: ignore[attr-defined]
        except Exception:
            pass
