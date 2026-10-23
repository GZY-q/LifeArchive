# Data model V1.0 — design rules

Schema is a **design draft**, not an applied migration. Codex should implement tables incrementally with Alembic per assigned task, not create every table in M0.

## Journals

- `users(id, username, password_hash, timezone, created_at, ...)`
- `sessions` or a robust secure-session equivalent; do not store plain tokens.
- `entries(id, user_id, content_md, entry_date DATE, occurred_at TIMESTAMPTZ NULL, occurred_timezone TEXT NULL, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ, deleted_at TIMESTAMPTZ NULL, revision INT, client_request_id UUID NULL)`
- `entry_revisions(id, entry_id, revision, content_md, entry_date, changed_at, editor_id)`
- `tags`, `entry_tags`
- `assets(id, owner_id, sha256, mime_type, byte_size, storage_key, created_at)`, `entry_assets`.

`entries.entry_date` is a calendar label chosen by user, not always the UTC date of `created_at`. Unique `(user_id, client_request_id)` where client id is non-null; real FK and indexes should be used. Revision must increment with optimistic version checks. Soft delete and permanent purge require explicit semantics for revisions, assets and indexes.

## News

- `news_sources`: feed/API config, enabled, license notes.
- `news_articles`: canonical URL/hash, source, title, published_at, collected_at, raw allowed metadata, fetch status.
- `world_events`: normalized event entity, event date/time + timezone/precision, topic, verification state.
- `event_articles`: many-to-many evidence references.
- `interest_topics`: per-owner topic/config.
- `daily_digests`: date, archive_timezone, version, status, published_at, model/prompt version.
- `digest_items`: digest, event, rank, immutable summary snapshot and referenced article IDs.

The daily digest **must retain its historical published version**; never silently overwrite a published digest. Corrections create a new version. News article/claim coverage must not imply historical truth without provenance.

## Job operations

- `jobs` (optional persistent schedules if user-configurable), `job_runs(id, job_type, target_date, idempotency_key UNIQUE, status, attempt_count, lease_until, started_at, finished_at, error, result_ref)`.
- `llm_runs` contains provider/model/prompt version, task metadata, cost estimates, status, duration; avoid storing private prompt data unnecessarily.
- `memory_links` (future): source entity, target entity, relation, evidence, human approval status.

## Indices and constraints

- `entries(user_id, entry_date DESC, created_at DESC)`;
- `news_articles(canonical_url)` unique where meaningful;
- event/date indexes; unique digest by `(date, archive_timezone, version)`;
- foreign keys, cascade/soft delete behavior explicit;
- use `TIMESTAMPTZ` for instants and `DATE` for archive/calendar days.

## Text search

PostgreSQL search first; evaluate Chinese segmentation and `pg_trgm` with actual test cases. pgvector is deferred and derived indexes must be rebuildable.
