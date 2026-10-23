# Task M1 (first slice) — Minimal secure journal

Execute ONLY after M0 is accepted.

## Scope

- Closed, private, single-owner login flow and session handling.
- Database schema for `users`, `entries`, and `entry_revisions` with Alembic; model `entry_date`, UTC timestamps, optimistic revision, client request dedup.
- CRUD API with request/response schemas, permission checks, pagination, proper 409 conflict behavior.
- Responsive entry composer/list using `@usememos/editor` only after verifying actual API, license and Chinese IME behavior; create an adapter component to avoid coupling whole application to library.
- Basic tests: create/edit/conflict/delete + owner restriction + Markdown content round-trip.

## Out of scope

News aggregation, autonomous agents, semantic search, public signup, social sharing, rich diagrams or editor fork.

## Acceptance

- When API+DB run without any worker or LLM, owner can create, list, edit, delete and view journal entries.
- Edits add revisions without losing prior Markdown text; conflict attempts never silently overwrite.
- Multiple records can belong to same `entry_date`, and backdated diary uses correct date.
- Tests and build pass; no secrets are committed.
