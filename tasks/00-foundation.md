# Task M0 — Create a runnable repository foundation

## Scope

Create the initial working repository for LifeArchive with:

- `apps/web`: React + Vite + TypeScript, simple branded Home page, basic navigation placeholder and health indicator. Use a stable package manager and commit the lockfile.
- `apps/server`: FastAPI application with `GET /api/v1/health`, Pydantic settings, database session module and Alembic migrations setup.
- Docker Compose: `web` (Caddy serving compiled SPA + reverse proxy `/api/*`), `api`, `worker` (same Python image, *placeholder process / no scheduler yet*), and `postgres`. Worker startup may be disabled by profile until there is a real task; avoid dummy busy loops.
- Configuration: `.env.example` with safe placeholders, `.gitignore`, Python/JS lint and format configs, minimal API and frontend tests, development README instructions.
- Secure baseline: PostgreSQL only on internal Docker network; no hardcoded secrets; Caddy route to API; persisted DB volume; simple non-sensitive health checks.

## Out of scope

Do NOT build journal CRUD, user management, image upload, news sources, AI integration, backup implementation, Kubernetes, Redis or microservices. Do not introduce Memos/Hermes service dependencies.

## Acceptance

1. `docker compose config` validates.
2. `docker compose up -d --build` starts the initial stack; web home loads and calls `/api/v1/health`.
3. PostgreSQL data volume persists after container restart (document how tested).
4. Alembic can connect to DB with no secrets in code and can run a smoke migration.
5. Backend test(s), lint checks, and frontend build succeed, with exact commands documented.
6. README documents how to stop, start, reset test data (destructive flag), and configure local environment.

## PR output

List changed paths, commands executed/results, technical defaults chosen, known limitations and clear next task M1. Acknowledge if full runtime tests cannot execute in current environment.
