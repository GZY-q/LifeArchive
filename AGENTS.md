# Codex instructions for LifeArchive

## What we are building

LifeArchive is a private, self-hosted, decades-long journal and world-history archive. The daily authoring experience should be as effortless as Memos, but the backend, data, and deployment belong entirely to LifeArchive. AI enriches history and memory; it never owns or silently rewrites the journal.

## Read before making changes

1. `README.md`
2. `docs/product.md`
3. `docs/architecture.md`
4. `docs/data-model.md`
5. The specific `tasks/*.md` task the user assigned

## Non-negotiable architecture constraints

- One repository; React/Vite TypeScript frontend; FastAPI Python backend; PostgreSQL main store; Docker Compose self-hosted deployment.
- No Memos service, no Hermes runtime, no Redis/Celery/Kafka/Kubernetes/Neo4j by default.
- Prefer tested existing libraries over custom reinvention. Memos editor is a candidate library; pin versions and verify React/IME/mobile compatibility before adopting.
- API process must never start the cron scheduler. Run jobs from a dedicated worker process using the same backend image.
- News ingestion is deterministic where possible; LLM only proposes structured classifications/summaries. Validate every proposal and referenced article ID server side.
- Journal originals and revisions must be separate from AI-derived summaries; do not send private journals to external LLMs by default.
- Store UTC instants as timezone-aware timestamps; preserve user-oriented `entry_date` and timezone where appropriate.
- Every job must be idempotent, retryable, and observable. Do not claim exactly-once execution.
- Keep secrets out of source control; no public database port, no unauthenticated private media.
- Plan for independent export and backup restore. Preserve raw Markdown and original media.

## How to work

- Complete **only the assigned task**. Do not implement future milestones opportunistically.
- First inspect current repository state. Outline short implementation plan, then make focused changes.
- Keep modules small, typed, tested, and documented. Prefer migrations over one-off SQL schema changes.
- Add or update tests for behavior you modify. Run relevant checks; state clearly which commands passed, failed, or were not run.
- Do not commit generated secrets, `.env`, credentials, private data, node_modules, or binary dumps.
- Ask for confirmation only when a security-sensitive, destructive, or major architectural decision is genuinely needed; otherwise choose a reasonable documented default.
- Open a PR with: what changed, how to run/test, migration impact, risks, and what remains.

## Delivery contract

Each task should end with: code + tests + docs updates + exact run instructions + verifiable acceptance results. Never label a scaffold as a finished feature.
