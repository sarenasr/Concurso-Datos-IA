# Manglar — Habla con los datos de Colombia

Manglar is an AI assistant for Colombian open data (datos.gov.co, a Socrata portal).
Users ask questions in natural Spanish; Manglar finds the right datasets, writes SoQL
queries, validates them, and returns an answer with a Vega-Lite chart, citations, and a
"Ver consulta" permalink so the result is auditable.

Built for the **Concurso Datos al Ecosistema 2026** hackathon.

## Architecture

```
                         +-----------------+
 Telegram  ------------> |   FastAPI app   | <------------ Next.js widget (Vercel)
 (webhook)               |   /chat (SSE)   |              (shadcn + SSE streaming)
                         +--------+--------+
                                  |
              +-------------------+--------------------+
              |                   |                    |
      +-------v-------+   +-------v--------+   +-------v------+
      |  LangGraph    |   |  RAG catalog   |   |  Graph       |
      |  agent+tools  |   |  pgvector 0.6v |   |  networkx    |
      |               |   |  + 0.4t fusion |   |              |
      +-------+-------+   +-------+--------+   +-------+------+
              |                    |                   |
              +-------+------+-----+------+------------+
                      |     |             |
              +-------v--+ +-v--------+ +--v--------+
              | Socrata  | | LiteLLM  | | Supabase  |
              | client   | | (LLM)    | | pgvector  |
              +----------+ +----------+ +-----------+
                      |
              +-------v------+  (same tools exposed to a local MCP client via stdio)
              |  FastMCP     |
              +--------------+
```

- **Backend** (`apps/backend`): Python, FastAPI + LangGraph agent + MCP server + RAG over the
  Socrata catalog stored in Supabase pgvector. LiteLLM makes the LLM provider-agnostic.
- **Frontend** (`apps/frontend`): Next.js 16 app-router + React 19 + TS + Tailwind + shadcn/ui.
  Streams answers via SSE (custom fetch-based parser), shows `SourcesCard`, "Ver consulta" button.
- **Storage** (`infra/supabase`): Supabase with pgvector. SQL migrations under
  `infra/supabase/migrations`.
- **Embeddings**: Google `gemini-embedding-2` (1024-dim) via OpenRouter (requires `OPENROUTER_API_KEY`).
- **LLM**: provider-agnostic via LiteLLM. OpenRouter is tried first; OpenCode Go (`glm-5.2`) is the fallback when no OpenRouter key is set or OpenRouter fails.
- **Deploy**: backend on Railway, frontend on Vercel.

## Setup

```bash
# 1. Environment — fill every variable in .env (see .env.example for reference)
cp .env.example .env

# 2. Supabase migrations
#    Apply infra/supabase/migrations/*.sql in order (Supabase Studio SQL editor):
#      001_catalog.sql -> 002_embeddings.sql -> 003_graph.sql -> 004_match_catalog.sql -> 005_fix_embedding_dim.sql
#    After 005 you must re-run scripts.build_embeddings (the migration truncates catalog_embeddings).

# 3. Backend (apps/backend)
cd apps/backend
uv sync
uv run python -m scripts.ingest_catalog          # load Socrata catalog into Supabase
uv run python -m scripts.build_embeddings        # embed catalog rows via Google gemini-embedding-2 over OpenRouter (requires OPENROUTER_API_KEY)
uv run python -m scripts.build_graph              # build the dataset graph
uv run uvicorn app.main:app --reload --port 8000  # start API

# 4. Frontend (apps/frontend)
cd apps/frontend
pnpm install
pnpm dev
```

## MCP server

Manglar ships a standalone [MCP](https://modelcontextprotocol.io) server (FastMCP) that exposes the same five
tools the agent uses — `search_catalog`, `get_schema`, `query_dataset`, `graph_neighbors`, `make_chart` — to
any local MCP client over **stdio**. It is launched by the client (it is not a network service and there is no
HTTP endpoint). It auto-loads the repo-root `.env`, so `search_catalog` / `graph_neighbors` need
`OPENROUTER_API_KEY` + Supabase configured, while `get_schema` / `query_dataset` only need `SOCRATA_*`.
`make_chart` needs nothing.

Run it directly (it will block, waiting for a client on stdin):

```bash
cd apps/backend
uv run python -m app.mcp_server.server
```

### Add to Claude

Claude Code — from the repo root:

```bash
claude mcp add manglar -- uv run --directory apps/backend python -m app.mcp_server.server
```

Claude Desktop — add to `claude_desktop_config.json` (`%APPDATA%\Claude\...` on Windows,
`~/Library/Application Support/Claude/...` on macOS):

```json
{
  "mcpServers": {
    "manglar": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/apps/backend", "python", "-m", "app.mcp_server.server"]
    }
  }
}
```

### Add to opencode

Add an `mcp` block to `opencode.json` (command paths are relative to the repo root):

```json
{
  "mcp": {
    "manglar": {
      "type": "local",
      "command": ["uv", "run", "--directory", "apps/backend", "python", "-m", "app.mcp_server.server"],
      "enabled": true
    }
  }
}
```

## Hero 10 (demo script)

1. ¿Cuántos contratos públicos firmó Medellín en 2025 y cuáles las top 5 empresas?
2. ¿Cuántos casos de COVID hubo en mi municipio en la última semana con datos?
3. ¿Empresas sancionadas que además tienen contratos en salud en Antioquia?
4. ¿Cuál fue la TRM promedio del último mes comparada con el año anterior?
5. ¿Qué datos abiertos existen sobre vacunación?
6. Verificá este tweet: "El gobierno contrató más en 2025 que en 2024".
7. ¿Qué hay de Antioquia en datos?
8. Analizá el déficit de viviendas en Bogotá usando datos abiertos.
9. ¿Cuántos medicamentos vigentes hay registrados y cuántos son del grupo cardiovasculares?
10. ¿Cuántos beneficiarios de Familias en Acción hay por municipio en Antioquia?

## Roadmap

- **Phase 1 (hackathon)**: catalog RAG + SoQL agent + self-correction + citations + Vega-Lite + MCP server.
- **Phase 2**: graph joins across sectors (NIT, municipio), claim-checker verdicts, auto-graph construction on full 10k catalog.
- **Phase 3**: proactive dashboards, multi-turn memory, WhatsApp/voice channels, indigenous-language support.
