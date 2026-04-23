# Architecture

_Deep-dive coming at Phase 6._

High-level components:

- **API** (`services/api/`) — FastAPI. Hosts the three agents (discovery, screening, drafting), the RAG retriever, and the LLM client.
- **UI** (`services/ui/`) — Streamlit multi-page app. Talks only to the API.
- **Orchestrator** (`services/n8n/`) — n8n workflows that call the API on a schedule and post to Slack.
- **Postgres + pgvector** — structured storage and vector index, run via Docker Compose.
