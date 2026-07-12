#!/bin/sh
set -e
cd /app/apps/backend
uv sync
exec uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}