# DATIA Project Instructions

## Project Overview

DATIA is an AI assistant for Colombian open data (datos.gov.co). Users ask questions in natural Spanish; DATIA finds the right datasets, writes SoQL queries, validates them, and returns answers with Vega-Lite charts, citations, and permalinks.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, LangGraph, Supabase/pgvector, LiteLLM, MCP
- **Frontend**: Next.js 16, React 19, TypeScript, Tailwind 4, shadcn/ui, Vercel AI SDK
- **Package managers**: uv (backend), pnpm (frontend)
- **Deploy**: Railway (backend), Vercel (frontend)

## Commands

### Backend
- `uv sync` — install dependencies
- `uv run uvicorn app.main:app --reload --port 8000` — start dev server
- `uv run pytest -v` — run tests
- `ruff check .` — lint
- `ruff format .` — format

### Frontend
- `pnpm install` — install dependencies
- `pnpm dev` — start dev server
- `pnpm build` — production build
- `pnpm lint` — lint

## Code Conventions

- Python: ruff (line-length 100), type hints required, async-first
- TypeScript: strict mode, no `any`, functional components
- GovCo accent color: `#FAB012`
- All user-facing text in Spanish
- Commit messages: conventional commits format

## Architecture Notes

- Backend agent uses LangGraph state graphs with tool nodes
- RAG catalog stored in Supabase pgvector (768-dim local embeddings via sentence-transformers)
- Frontend streams via SSE using Vercel AI SDK
- MCP server exposes same tools to external clients via FastMCP

## Subagent Model Selection (IMPORTANT)

When dispatching Task subagents, use cheaper OpenCode Go models — NOT the default GLM-5.2:

- **Very easy tasks** (file edits, simple scripts, formatting): `mimo-v2.5` or `deepseek-v4-flash`
- **Standard coding tasks** (components, endpoints, tools): `qwen3.7-plus`
- **Hard tasks** (complex logic, architecture, debugging): `kimi-k2.7-code`

This conserves GLM-5.2 tokens for planning and review only.
