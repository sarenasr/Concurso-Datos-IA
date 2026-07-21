# Manglar Project Instructions

## Project Overview

Manglar is an AI assistant for Colombian open data (datos.gov.co). Users ask questions in natural Spanish; Manglar finds the right datasets, writes SoQL queries, validates them, and returns answers with Vega-Lite charts, citations, and permalinks.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, LangGraph, Supabase/pgvector, LiteLLM, MCP
- **Frontend**: Next.js 16, React 19, TypeScript, Tailwind 4, shadcn/ui
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
- Brand: see `DESIGN.md` — Manglar palette (primary `#1b3f92`), Geologica font, `-0.99px` headline tracking
- All user-facing text in Spanish
- Commit messages: conventional commits format

## Architecture Notes

- Backend agent uses LangGraph state graphs with tool nodes
- RAG catalog stored in Supabase pgvector (1024-dim embeddings via Google gemini-embedding-2 over OpenRouter)
- Frontend streams via SSE using a custom fetch-based parser
- MCP server exposes the same tools to a local MCP client (stdio) via FastMCP

## Subagent Model Selection (IMPORTANT)

When dispatching Task subagents, use cheaper OpenCode Go models — NOT the default GLM-5.2:

- **Very easy tasks** (file edits, simple scripts, formatting): `mimo-v2.5` or `deepseek-v4-flash`
- **Standard coding tasks** (components, endpoints, tools): `qwen3.7-plus`
- **Hard tasks** (complex logic, architecture, debugging): `kimi-k2.7-code`

This conserves GLM-5.2 tokens for planning and review only.

These overrides are configured in `opencode.json`. After editing it, restart opencode for changes to take effect.

## Subagent Skill Usage (IMPORTANT)

Subagents MUST load relevant skills before starting work. When dispatching subagents, instruct them to use the `skill` tool with these skill names as appropriate:

- **Backend agent/RAG work**: `langgraph-patterns`, `socrata-soql`, `systematic-debugging`
- **Frontend UI work**: `frontend-design`, `vega-lite`, `ui-ux-pro-max`
- **MCP server work**: `mcp-builder`
- **Any coding task**: `test-driven-development`, `verification-before-completion`
- **Planning/architecture**: `writing-plans`, `brainstorming`
- **Debugging**: `systematic-debugging`
