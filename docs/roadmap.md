# Development roadmap and acceptance gates

## Milestones

### M0 — repository foundation (first Codex task)
- Monorepo React/Vite TS + FastAPI + PostgreSQL, Docker Compose, Caddy (development-friendly), health endpoint, Alembic foundation, lints/test scaffolding, README run instructions.
- Acceptance: from clean clone, `docker compose up -d --build`, `/api/v1/health` returns JSON; PostgreSQL persists after restart; basic frontend loads; test/lint commands documented and pass.
- No journal CRUD, news, auth or AI in M0.

### M1 — journal essentials
- Closed-owner login, Markdown editor adapter, entry CRUD with optimistic revision/creation idempotency, tags, list and day grouping. Add assets and edit history in prioritized slices.
- Acceptance: journal works when worker/LLM disabled; mobile inputs work including Chinese IME; data persists across restart; tests pass.

### M2 — archive/day views
- Calendar month, Daily Capsule with journal side; basic search, timezone correctness, `On this day`.
- Acceptance: date assignment and late-backfill work without confusing creation date.

### M3 — news ingestion
- RSS/API sources, source metadata, dedup, event association, job ledger, retries and observability.
- Acceptance: a week of replayable sample fixtures doesn't create duplicates or lose provenance.

### M4 — LLM-curated digests
- LLM adapter, prompt/schema version, structured summary, strict source references, versioned daily digest, interest filtering.
- Acceptance: can re-run a day safely, list cited sources, and operate journal without AI availability.

### M5 — VPS reliability release
- Hardened Caddy/Compose, access controls, private media, encrypted offsite backups, export, verified restore, docs.
- Acceptance: cold restore onto a fresh environment with journal/media/news continuity.

## Execution agreement

One milestone is not one giant PR. Keep PRs small and independently testable. Do not implement next milestone until the current task's acceptance checks pass.
