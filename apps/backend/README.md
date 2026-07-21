# Manglar backend

FastAPI + LangGraph agent + MCP server + RAG over the Socrata catalog.

See the root `README.md` for setup. Key entrypoints:

- API: `uv run uvicorn app.main:app --reload`
- Agent: `app.agents.graph:run_agent(question)`
- MCP server: `uv run python -m app.mcp_server.server`
- Telegram bot (polling): `uv run python -m app.channels.telegram_bot`

## Scripts (run in order)

```bash
uv run python -m scripts.ingest_catalog      # load catalog into Supabase
uv run python -m scripts.build_embeddings    # embed catalog rows (Gemini)
uv run python -m scripts.build_graph         # build dataset knowledge graph
```
