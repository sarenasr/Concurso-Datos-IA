# Manglar frontend

Next.js 16 (app router) + React 19 + TypeScript + Tailwind CSS 4 + shadcn/ui. Renders the
chat widget that talks to the FastAPI backend over SSE.

See the root [`README.md`](../../README.md) for the full-stack setup and architecture.

## Commands

```bash
pnpm install       # install dependencies
pnpm dev           # start dev server on http://localhost:3000
pnpm build          # production build (also run in CI)
pnpm lint          # eslint
```

## Config

- `NEXT_PUBLIC_BACKEND_URL` — base URL of the FastAPI backend (defaults to `localhost:8000` in dev).
- `pnpm-workspace.yaml` pins `onlyBuiltDependencies` for `sharp`/`unrs-resolver`'s native
  postinstall scripts — required for `pnpm install --frozen-lockfile` to succeed non-interactively
  (as CI does); without it pnpm blocks on approving build scripts.

## Structure

- `app/` — routes (`/`, `/datos`) and layout.
- `components/` — chat UI (`chat.tsx`), `SourcesCard`, shadcn primitives under `components/ui/`.
- `lib/` — SSE fetch-based stream parser and API client helpers.
