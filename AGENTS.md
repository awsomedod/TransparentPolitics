# AGENTS.md

## Cursor Cloud specific instructions

### Architecture Overview

TransparentPolitics is a three-tier application:
- **Backend**: FastAPI (Python 3.12) on port 8000
- **Frontend**: Next.js 15 (TypeScript) on port 3001
- **ETL**: Dagster pipelines (optional for basic dev)

Infrastructure is defined in `infra/docker-compose.yml`.

### Required Services

| Service | How to Start | Port |
|---------|-------------|------|
| PostgreSQL + PostGIS | `sudo docker compose -f infra/docker-compose.yml up -d postgres` | 5432 |
| Redis | `sudo docker compose -f infra/docker-compose.yml up -d redis` | 6379 |
| FastAPI backend | `cd backend && fastapi dev app/main.py --port 8000` | 8000 |
| Next.js frontend | `cd frontend && npm run dev` | 3001 |

### Starting the Docker daemon

The VM runs inside a nested container, so Docker requires special configuration (already set up):
```
sudo dockerd &>/tmp/dockerd.log &
```
Wait a few seconds after starting before running Docker commands.

### Environment Setup

- `.env` at repo root: copy from `.env.example` (defaults work locally for dev)
- Backend reads `DATABASE_URL` from `.env` or defaults in `backend/app/core/config.py`
- The frontend proxies `/api/*` to `http://localhost:8000` via `next.config.ts` rewrites

### Running Migrations

```
cd backend && alembic upgrade head
```

### Lint / Type-check / Test Commands

| Scope | Command | Notes |
|-------|---------|-------|
| Backend lint | `cd backend && ruff check .` | Pre-existing import-sort issues in alembic/ |
| Backend type check | `cd backend && mypy app/` | Passes clean |
| Backend tests | `cd backend && pytest` | No tests written yet (Phase 1) |
| Frontend lint | `cd frontend && npx next lint` | Passes clean |
| Frontend type check | `cd frontend && npx tsc --noEmit` | Passes clean |

### Gotchas

- Python tools (`fastapi`, `alembic`, `ruff`, `pytest`, `mypy`) install to `~/.local/bin` — ensure it's on PATH.
- The frontend has no lockfile; `npm install` resolves from `package.json` each time.
- `ruff check` reports pre-existing lint issues in `alembic/` (import sorting, trailing whitespace) that are not from your changes.
- MinIO and OpenSearch are optional for local development; only PostgreSQL and Redis are required.
