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
