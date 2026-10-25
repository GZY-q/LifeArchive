# Architecture decision record (living)

## ADR-001 — Independent application
Status: accepted. Borrow Memos UX and optionally use its separately packaged editor. Never require Memos backend. Verify editor package license/version before adding.

## ADR-002 — No Hermes deployment
Status: accepted. Extract only useful ideas: scheduled work, structured LLM summarization, strict tool boundaries, persistent job tracking. No agent framework runtime.

## ADR-003 — Modular monolith
Status: accepted. FastAPI modular backend with an independent worker command; PostgreSQL as primary store, Compose deployment on private VPS. Defer queues and distributed services.

## ADR-004 — Original data outranks AI
Status: accepted. Original Markdown, revisions and media are preserved; AI summaries are derived and replaceable. No unapproved editing of source diary.

## ADR-005 — Timeline-first and date-aware
Status: accepted. Keep `entry_date`, real timestamps, source publication time, event time, timezone and snapshot version separate. Temporal coincidence does not establish causality.

## ADR-006 — Search incrementally
Status: accepted. Start with keyword/date/tag query; validate Chinese search. Add hybrid semantic search only when essential.

## ADR-007 — M0 development baseline
Status: accepted for M0. npm + package-lock and uv + uv.lock lock the two dependency graphs. Keep the frontend as a small React page with plain CSS; editor, UI library and authentication decisions remain for their assigned milestones. Use synchronous SQLAlchemy 2 + psycopg 3 sessions, with transaction ownership explicit in future services. The health endpoint is liveness only and initializes neither database connections nor scheduling.

Compose exposes only a loopback HTTP Web port. PostgreSQL 17 is on an internal network with a named volume. Alembic migrations are explicit commands; the initial revision has no business tables. The worker shares the API image but is behind a profile and exits immediately in M0. This development baseline does not satisfy the later production authentication, HTTPS, export or backup gates.

## ADR-008 — M1 private journal boundary
Status: accepted for M1. Initialize one owner through a local CLI only, guarded by a database singleton constraint. Use Argon2id and revocable opaque cookie sessions; persist session digests, derive per-session CSRF tokens and verify exact trusted origins. Share the login attempt budget through PostgreSQL rather than process memory or a new queue/cache service.

Use an atomic revision compare-and-swap plus a revision snapshot in one transaction. Scope all reads and mutations to the authenticated owner. Creation request IDs deduplicate against the original revision; soft deletion never resurrects a record on retry. Preserve raw Markdown and render it as text. A small textarea adapter is the current editor until the Memos package passes the required IME/mobile compatibility matrix; do not couple storage to its document model.

## ADR-009 — M2 calendar as a read model
Status: accepted for M2's first slice. Query the existing journal tables and owner/date index for sparse monthly counts. Use the explicit `entry_date` label, including backdated entries; never infer it from UTC creation timestamps. Reuse journal pagination for day reads and omit deleted/other-owner entries. No derived calendar tables, migration, worker or news fields are needed. Keep the authenticated journal workspace and its draft available when browsing the calendar; switching views must not create writes or discard uncertain requests.

## ADR-010 — Private literal search before full-text indexing
Status: accepted for M2's second slice. Use an authenticated, CSRF-protected read-only POST so journal search terms are carried in JSON instead of URLs and ordinary access logs. Search current originals with a parameterized, escaped, case-insensitive substring and optional inclusive archive-date bounds. Use a separate versioned cursor with a digest of owner and normalized filters; do not put query text in cursors. Keep search inputs only in page memory, submit explicitly, and paginate the submitted filter snapshot. This is a small-archive baseline; measure real Chinese datasets before adding pg_trgm, segmentation, migrations or a new service.
