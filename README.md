<img width="1538" height="1375" alt="LOGOTIPO CLARO" src="https://github.com/user-attachments/assets/30a086f0-d71f-4b8c-9880-5948b762b1e5" />

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
- **Retrieval**: hybrid RAG (pgvector cosine + Postgres FTS, fused with RRF) + a Cohere
  `rerank-4-pro` cross-encoder pass, plus a curated priority-dataset boost with a
  vector-support gate to avoid force-ranking off-topic keyword matches.
- **Embeddings**: Google `gemini-embedding-2` (1024-dim) via OpenRouter (requires `OPENROUTER_API_KEY`).
- **LLM**: `anthropic/claude-sonnet-4.5` for both the answer/SoQL-writer model and the
  hot-path (triage/join) model, routed through LiteLLM. `LITELLM_API_BASE` can point
  LiteLLM at any other OpenAI-compatible endpoint instead.
- **Deploy**: backend on Railway, frontend on Vercel.

## Features

- **Chat over your data, in Spanish** — ask a natural-language question, get a written answer,
  a citation to the source dataset(s), and (when the result is tabular) an auto-generated
  Vega-Lite chart. Streamed token-by-token over SSE (`POST /chat`); the frontend also supports
  a non-streaming JSON mode (`{"stream": false}`).
- **Auditable by construction** — every answer ships the exact SoQL query that produced it and
  a "Ver consulta" permalink that re-runs it directly against `datos.gov.co` (proxied via
  `GET /api/query`), so any number can be independently verified.
- **Dataset pinning** — paste a Socrata dataset id (`xxxx-xxxx`) or a `datos.gov.co` link into
  the chat and the agent skips RAG search entirely, going straight to that dataset's schema and
  SoQL generation.
- **Hybrid retrieval** — dense pgvector cosine search + Postgres full-text search fused with
  RRF, then a Cohere `rerank-4-pro` cross-encoder pass, plus a curated priority-dataset boost
  gated on genuine vector similarity (so a bare keyword hit can't force-rank an off-topic
  dataset to the top).
- **Self-correcting SoQL** — if a generated query fails against Socrata, the agent feeds the
  error back into the LLM and retries (bounded number of attempts) before giving up and
  suggesting alternative datasets.
- **Cross-sector joins** — a `networkx` dataset graph (built from LLM column classification +
  Jaccard similarity on sampled values) lets the agent join across datasets sharing a key like
  NIT or municipio, for questions that span more than one sector.
- **Honest abstention** — when no dataset is confidently relevant, the agent says so instead of
  guessing, and links out to its best (unconfirmed) guesses as clickable suggestions.
- **Multi-channel**: the same LangGraph agent is exposed over the Next.js chat widget, a
  Telegram bot (`app.channels.telegram_bot`, long-polling), and an MCP server (below) for use
  from any MCP-compatible client.
- **`/health`** — liveness + readiness probe (checks Supabase connectivity, cached 10s).

## Setup

```bash
# 1. Environment — fill every variable in .env (see .env.example for reference)
cp .env.example .env

# 2. Supabase migrations
#    Apply infra/supabase/migrations/*.sql in order (Supabase Studio SQL editor):
#      001_catalog.sql -> 002_embeddings.sql -> 003_graph.sql -> 004_match_catalog.sql ->
#      005_fix_embedding_dim.sql -> 006_filter_catalog_datasets.sql -> 007_fts.sql
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

## Development

```bash
# Backend (apps/backend)
uv run ruff check .
uv run ruff format .
uv run pytest -v

# Frontend (apps/frontend)
pnpm lint
pnpm build
```

CI (`.github/workflows/ci.yml`) runs on every push and pull request against `main`:
backend lint/format/tests, frontend install/lint/build, and a migrations smoke test that
spins up a `pgvector/pgvector:pg16` service container, applies every file in
`infra/supabase/migrations` in order, and exercises the `match_catalog` RPC.
