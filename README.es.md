# Manglar — Habla con los datos de Colombia

*[Read this in English](README.md)*

Manglar es un asistente de IA para los datos abiertos de Colombia (datos.gov.co, un portal
Socrata). Los usuarios hacen preguntas en español natural; Manglar encuentra los datasets
correctos, escribe consultas SoQL, las valida, y devuelve una respuesta con un gráfico
Vega-Lite, citas de la fuente, y un enlace "Ver consulta" para que el resultado sea auditable.

Construido para el **Concurso Datos al Ecosistema 2026**.

## Arquitectura

```
                         +-----------------+
 Telegram  ------------> |   FastAPI app   | <------------ Widget Next.js (Vercel)
 (webhook)               |   /chat (SSE)   |              (shadcn + streaming SSE)
                         +--------+--------+
                                  |
              +-------------------+--------------------+
              |                   |                    |
      +-------v-------+   +-------v--------+   +-------v------+
      |  Agente       |   |  Catálogo RAG  |   |  Grafo       |
      |  LangGraph    |   |  pgvector 0.6v |   |  networkx    |
      |  + tools      |   |  + 0.4t fusion |   |              |
      +-------+-------+   +-------+--------+   +-------+------+
              |                    |                   |
              +-------+------+-----+------+------------+
                      |     |             |
              +-------v--+ +-v--------+ +--v--------+
              | Cliente  | | LiteLLM  | | Supabase  |
              | Socrata  | | (LLM)    | | pgvector  |
              +----------+ +----------+ +-----------+
                      |
              +-------v------+  (las mismas tools expuestas a un cliente MCP local vía stdio)
              |  FastMCP     |
              +--------------+
```

- **Backend** (`apps/backend`): Python, FastAPI + agente LangGraph + servidor MCP + RAG sobre el
  catálogo de Socrata almacenado en Supabase pgvector. LiteLLM hace que el proveedor de LLM sea
  intercambiable.
- **Frontend** (`apps/frontend`): Next.js 16 app-router + React 19 + TS + Tailwind + shadcn/ui.
  Transmite respuestas vía SSE (parser custom basado en fetch), muestra `SourcesCard`, botón
  "Ver consulta".
- **Almacenamiento** (`infra/supabase`): Supabase con pgvector. Migraciones SQL en
  `infra/supabase/migrations`.
- **Recuperación**: RAG híbrido (coseno pgvector + FTS de Postgres, fusionados con RRF) + un paso
  de reranking cross-encoder con Cohere `rerank-4-pro`, más un boost de datasets prioritarios
  curados con una compuerta de soporte vectorial para evitar forzar el ranking de coincidencias
  de palabras clave fuera de tema.
- **Embeddings**: `gemini-embedding-2` de Google (1024 dim) vía OpenRouter (requiere
  `OPENROUTER_API_KEY`).
- **LLM**: `anthropic/claude-sonnet-4.5` tanto para el modelo de respuesta/escritura de SoQL como
  para el modelo del hot-path (triage/join), enrutado vía LiteLLM. `LITELLM_API_BASE` puede
  apuntar LiteLLM a cualquier otro endpoint compatible con OpenAI.
- **Deploy**: backend en Railway, frontend en Vercel.

## Funcionalidades

- **Chat sobre tus datos, en español** — hacé una pregunta en lenguaje natural y recibí una
  respuesta escrita, una cita al dataset(s) fuente, y (cuando el resultado es tabular) un gráfico
  Vega-Lite generado automáticamente. Transmitido token por token vía SSE (`POST /chat`); el
  frontend también soporta un modo JSON sin streaming (`{"stream": false}`).
- **Auditable por construcción** — cada respuesta incluye la consulta SoQL exacta que la produjo
  y un enlace "Ver consulta" que la vuelve a ejecutar directamente contra `datos.gov.co`
  (mediante proxy en `GET /api/query`), para que cualquier número pueda verificarse de forma
  independiente.
- **Fijado de dataset** — pegá un id de dataset de Socrata (`xxxx-xxxx`) o un link de
  `datos.gov.co` en el chat y el agente omite la búsqueda RAG por completo, yendo directo al
  schema de ese dataset y a la generación de SoQL.
- **Recuperación híbrida** — búsqueda densa por coseno pgvector + búsqueda de texto completo de
  Postgres fusionadas con RRF, luego un paso de reranking cross-encoder con Cohere
  `rerank-4-pro`, más un boost de datasets prioritarios curados que exige similitud vectorial
  genuina (para que una coincidencia de palabra clave suelta no fuerce el ranking de un dataset
  fuera de tema).
- **SoQL autocorregible** — si una consulta generada falla contra Socrata, el agente retroalimenta
  el error al LLM y reintenta (con un número acotado de intentos) antes de rendirse y sugerir
  datasets alternativos.
- **Joins entre sectores** — un grafo de datasets con `networkx` (construido a partir de
  clasificación de columnas por LLM + similitud de Jaccard sobre valores muestreados) le permite
  al agente unir datasets que comparten una clave como NIT o municipio, para preguntas que
  abarcan más de un sector.
- **Abstención honesta** — cuando ningún dataset es lo bastante relevante, el agente lo dice en
  vez de adivinar, y enlaza sus mejores sugerencias (sin confirmar) como opciones clicables.
- **Multicanal**: el mismo agente LangGraph se expone a través del widget de chat en Next.js, un
  bot de Telegram (`app.channels.telegram_bot`, long-polling), y un servidor MCP (abajo) para uso
  desde cualquier cliente compatible con MCP.
- **`/health`** — probe de liveness + readiness (chequea conectividad a Supabase, cacheado 10s).

## Instalación

```bash
# 1. Entorno — completá cada variable en .env (ver .env.example de referencia)
cp .env.example .env

# 2. Migraciones de Supabase
#    Aplicá infra/supabase/migrations/*.sql en orden (SQL editor de Supabase Studio):
#      001_catalog.sql -> 002_embeddings.sql -> 003_graph.sql -> 004_match_catalog.sql ->
#      005_fix_embedding_dim.sql -> 006_filter_catalog_datasets.sql -> 007_fts.sql
#    Después de 005 hay que volver a correr scripts.build_embeddings (la migración vacía catalog_embeddings).

# 3. Backend (apps/backend)
cd apps/backend
uv sync
uv run python -m scripts.ingest_catalog          # cargar el catálogo de Socrata en Supabase
uv run python -m scripts.build_embeddings        # generar embeddings del catálogo con Google gemini-embedding-2 vía OpenRouter (requiere OPENROUTER_API_KEY)
uv run python -m scripts.build_graph              # construir el grafo de datasets
uv run uvicorn app.main:app --reload --port 8000  # levantar la API

# 4. Frontend (apps/frontend)
cd apps/frontend
pnpm install
pnpm dev
```

## Servidor MCP

Manglar incluye un servidor [MCP](https://modelcontextprotocol.io) independiente (FastMCP) que
expone las mismas cinco tools que usa el agente — `search_catalog`, `get_schema`,
`query_dataset`, `graph_neighbors`, `make_chart` — a cualquier cliente MCP local vía **stdio**.
Lo lanza el cliente (no es un servicio de red, no hay endpoint HTTP). Carga automáticamente el
`.env` de la raíz del repo, por lo que `search_catalog` / `graph_neighbors` necesitan
`OPENROUTER_API_KEY` + Supabase configurados, mientras que `get_schema` / `query_dataset` solo
necesitan `SOCRATA_*`. `make_chart` no necesita nada.

Ejecutarlo directamente (queda bloqueado esperando un cliente en stdin):

```bash
cd apps/backend
uv run python -m app.mcp_server.server
```

### Agregar a Claude

Claude Code — desde la raíz del repo:

```bash
claude mcp add manglar -- uv run --directory apps/backend python -m app.mcp_server.server
```

Claude Desktop — agregar a `claude_desktop_config.json` (`%APPDATA%\Claude\...` en Windows,
`~/Library/Application Support/Claude/...` en macOS):

```json
{
  "mcpServers": {
    "manglar": {
      "command": "uv",
      "args": ["run", "--directory", "/ruta/absoluta/a/apps/backend", "python", "-m", "app.mcp_server.server"]
    }
  }
}
```

### Agregar a opencode

Agregar un bloque `mcp` a `opencode.json` (las rutas de comando son relativas a la raíz del
repo):

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

## Hero 10 (guion de demo)

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

- **Fase 1 (hackathon)**: RAG del catálogo + agente SoQL + autocorrección + citas + Vega-Lite + servidor MCP.
- **Fase 2**: joins de grafo entre sectores (NIT, municipio), veredictos de verificación de afirmaciones, construcción automática del grafo sobre el catálogo completo de 10k.
- **Fase 3**: dashboards proactivos, memoria multi-turno, canales de WhatsApp/voz, soporte de lenguas indígenas.

## Desarrollo

```bash
# Backend (apps/backend)
uv run ruff check .
uv run ruff format .
uv run pytest -v

# Frontend (apps/frontend)
pnpm lint
pnpm build
```

CI (`.github/workflows/ci.yml`) corre en cada push y pull request contra `main`:
lint/format/tests del backend, install/lint/build del frontend, y una prueba de humo de
migraciones que levanta un contenedor de servicio `pgvector/pgvector:pg16`, aplica cada archivo
en `infra/supabase/migrations` en orden, y ejercita el RPC `match_catalog`.
