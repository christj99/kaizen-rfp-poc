"""FastAPI entrypoint.

Phase 0 exposes only /health so the startup scripts can verify the service is up.
Agent endpoints are added in Phase 2.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Kaizen RFP POC", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
