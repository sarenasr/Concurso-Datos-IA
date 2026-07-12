FROM python:3.11-slim

RUN pip install uv

WORKDIR /app

COPY apps/backend/pyproject.toml apps/backend/uv.lock ./apps/backend/
RUN cd apps/backend && uv sync

COPY apps/backend/ ./apps/backend/

WORKDIR /app/apps/backend

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]