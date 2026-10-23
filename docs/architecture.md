# Architecture — LifeArchive V1.0

## Decision: modular monolith + isolated worker

```text
Desktop / Mobile browser
         |
      Caddy (HTTPS, static React)
         |
       FastAPI API ───── PostgreSQL
         |                   ^
    private media             |
                             |
      Worker process (same Python backend image)
          |- APScheduler 3.x (triggers only)
          |- job executor + PostgreSQL job ledger
          |- RSS/API collectors + dedup/event grouping
          |- structured LLM curator + validator
```

Single Git repository, one Docker Compose project, four logical containers: web/proxy, API, worker, postgres. Avoid managing Hermes or Memos service. External LLM is a configurable optional outbound dependency. Never expose DB/worker ports publicly.

## Domain components

- journal: journal entries, versioning, tags, trash, day assignment.
- media: authenticated access, upload metadata, file integrity, exports.
- news: sources, fetched articles, dedup, world event clusters, digest versions.
- timeline: date-centered aggregation, no artificial links for coincident events.
- search: scoped text/date/tag search (evaluate Chinese tokenization in real data).
- jobs: durable job state, locking/lease, retries, idempotency, visibility.
- ai: LLM adapter, prompt versioning, Pydantic schemas, provider abstraction.

## Write boundaries

- API and worker use services/repositories with transactions and validation. An AI output is always a proposal; the server is the authority for persistence.
- Journal edits create revision records in a single transaction. Client saves should support optimistic concurrency and idempotent creation.
- Worker: use DB-backed `job_runs` with uniqueness for job type + archive date + version (where appropriate), lease/recovery and bounded retries. Scheduler is a trigger, not a source of truth.
- Two timestamps may describe the same item: event or entry occurrence and collection/record creation. Preserve original timezone and human date.

## News pipeline

`source fetch → normalize → dedup → cluster → select → LLM summarize → validate source IDs/dates/schema → publish versioned digest`.

Keep source article metadata and publication times, respect robots/content licenses, and keep uncertainty/verification statuses. Multiple articles can describe one event; digest is a snapshot of the current understanding rather than a duplicate record corpus.

## Deployment and growth

- Build frontend static files, serve with Caddy; FastAPI behind HTTPS proxy.
- API and worker run same Python app image using separate startup commands.
- Save durable database and media volumes, external encrypted backups.
- Future: object storage adapter, pgvector, multiuser, separate worker host. Avoid implementing these until use cases justify them.

## Maintainability

- Explicit API versioning `/api/v1` and Alembic revisions.
- Editable Markdown primary; third-party editor must not impose proprietary storage.
- Contract tests around date aggregation and job idempotency, plus backup restore rehearsal.
