# DATIA — Habla con los datos de Colombia

DATIA is an AI assistant for Colombian open data (datos.gov.co, a Socrata portal).
Users ask questions in natural Spanish; DATIA finds the right datasets, writes SoQL
queries, validates them, and returns an answer with a Vega-Lite chart, citations, and a
"Ver consulta" permalink so the result is auditable.

Built for the **Concurso Datos al Ecosistema 2026** hackathon.

## Architecture

```
                          +-----------------+
        Telegram  ----->  |   FastAPI app   |  <-----  Next.js widget (Vercel)
        (webhook)         |  /chat (SSE)    |          (shadcn + Vercel AI SDK)
                          +--------+-------+
                                   |
              +--------------------+-------------------+
              |                    |                   |
      +-------v-------+   +--------v-------+   +------v------+
      |  LangGraph    |   |  RAG catalog   |   |  Graph      |
      |  agent (tools)|   |  pgvector RRF   |   |  networkx   |
      +-------+-------+   +--------+-------+   +------+------+
              |                    |                  |
              +-------+-------+-----+------+-----------+
                      |            |      |
                +-----v----+  +----v---+ +-v--------+
                | Socrata  |  | LiteLLM| | Supabase |
                | client   |  | (LLM)  | | pgvector |
                +----------+  +--------+ +----------+
                      |
                +-----v------+
                |  FastMCP   |  (same tools exposed to external MCP clients)
                +-----------+
```

- **Backend** (`apps/backend`): Python, FastAPI + LangGraph agent + MCP server + RAG over the
  Socrata catalog stored in Supabase pgvector. LiteLLM makes the LLM provider-agnostic.
- **Frontend** (`apps/frontend`): Next.js 14 app-router + TS + Tailwind + shadcn/ui +
  Vercel AI SDK. Streams answers, shows `SourcesCard`, "Ver consulta" button.
- **Storage** (`infra/supabase`): Supabase with pgvector. SQL migrations under
  `infra/supabase/migrations`.
- **Embeddings**: `paraphrase-multilingual-mpnet-base-v2` (768-dim) via sentence-transformers (local, no API key). Gemini `gemini-embedding-001` supported as alternative via config.
- **LLM**: provider-agnostic via LiteLLM. Defaults to OpenCode Go (`glm-5.2`) or any OpenAI-compatible endpoint.
- **Deploy**: backend on Railway (`infra/railway.toml`), frontend on Vercel.

## Setup

```bash
# 1. Environment
cp .env.example .env          # fill every variable

# 2. Supabase migrations
#    Apply infra/supabase/migrations/*.sql in order (Supabase Studio SQL editor):
#      001_catalog.sql -> 002_embeddings.sql -> 003_graph.sql

# 3. Backend (apps/backend)
cd apps/backend
uv sync
uv run python -m scripts.ingest_catalog          # load Socrata catalog into Supabase
uv run python -m scripts.build_embeddings        # embed catalog rows (local sentence-transformers, ~1.1GB download on first run)
uv run python -m scripts.pull_schemas             # fetch schemas for priority datasets
uv run python -m scripts.build_graph              # build the dataset graph
uv run uvicorn app.main:app --reload --port 8000  # start API

# 4. Frontend (apps/frontend)
cd apps/frontend
pnpm install
pnpm dev
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
