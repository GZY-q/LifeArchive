# Data model V1.0 — design rules

Schema is a **design draft**, not an applied migration. Codex should implement tables incrementally with Alembic per assigned task, not create every table in M0.

## Journals

- `users(id, username, password_hash, timezone, created_at, ...)`
- `sessions` or a robust secure-session equivalent; do not store plain tokens.
- `entries(id, user_id, content_md, entry_date DATE, occurred_at TIMESTAMPTZ NULL, occurred_timezone TEXT NULL, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ, deleted_at TIMESTAMPTZ NULL, revision INT, client_request_id UUID NULL, is_pinned BOOLEAN)`
- `entry_revisions(id, entry_id, revision, content_md, entry_date, changed_at, editor_id, tags JSONB, assets JSONB, is_pinned BOOLEAN)`
- `tags(id, user_id, name, name_key, created_at)`; unique `(user_id,name_key)`.
- `entry_tags(entry_id, tag_id, user_id)`; primary key `(entry_id,tag_id)` and composite owner foreign keys to entries/tags.
- `assets(id, user_id, sha256, mime_type, byte_size, width, height, storage_key, created_at)`; unique `(user_id,sha256)` and `(id,user_id)`.
- `entry_assets(entry_id,asset_id,user_id)`; composite owner foreign keys, primary key `(entry_id,asset_id)`.

`entries.entry_date` is a calendar label chosen by user, not always the UTC date of `created_at`. Unique `(user_id, client_request_id)` where client id is non-null; real FK and indexes should be used. Revision must increment with optimistic version checks. Soft delete and permanent purge require explicit semantics for revisions, assets and indexes.

Task 08 applies tags with `0004_entry_tags`. Names use trimmed NFC for display and NFKC + casefold for owner-scoped uniqueness. An entry has at most 20 tags. Tags and journal fields share one revision/CAS transaction; immutable revision `tags` stores UUID/name snapshots, sorted by UUID. Existing revisions receive `[]`. Tag IDs do not alter raw Markdown. Creation replay compares revision 1's tag-ID set alongside the original text/date. Tag rename/delete and tag hierarchies remain deferred.

Task 09 reuses these tables without a migration. Restore atomically matches owner, non-null `deleted_at`, and expected revision; clears deletion, increments revision, updates the UTC modification instant, and saves an immutable content/date/tag snapshot. IDs, creation request UUIDs, original dates, occurrence metadata, and historical revisions survive delete/restore cycles. Repeated or stale restore requests conflict; no permanent purge exists. The recycle-bin cursor orders by `(deleted_at DESC,id DESC)` and binds owner separately from journal cursors. No performance guarantee for large recycle bins is made yet.

Task 11 applies `0005_private_images`, adds the asset tables and `entry_revisions.assets JSONB` (old snapshots `[]`). Current/revision asset metadata contains public ID, MIME, byte count, SHA-256, dimensions and UTC creation instant; private storage keys never enter API/export metadata. Images are immutable original files under UUID-hex keys in a private volume. Entries reference at most ten owner assets; association changes share the journal CAS/transaction and creation replay compares revision 1's asset-ID set. Detaching/soft deleting never destroys history or media. Per-owner row locking serializes content-hash deduplication and registered-byte quota checks. Files become durable before DB metadata commits; failed writes can retain unregistered files, never overwrite existing originals. Metadata and private file volume must be backed up together.

Task12 adds `0006_journal_pinning`: current and historical is_pinned default false, plus an active owner/pin/date/created/id index. Pin updates share revision CAS, preserve archive dates and create snapshots. Only explicit `order=pinned` journal lists group pins first; calendar/day/search/on-this-day keep date semantics. Cursors bind the order, old date cursors remain compatible. Soft delete/restore retains pin state; creation replay compares revision1's pin value. Portable format v4 exports current/historical pin state without changing media paths.

Task13 reuses User/AuthSession/LoginThrottle with no migration. Password change and session revocation reserve the existing shared attempt budget before acquiring the User lock. They refresh the locked owner, recheck the requesting session against the current database clock, verify the password, then commit the hash update (if any), old-session revocation, and new opaque session atomically. Login also holds the owner lock from fresh password verification through session commit to prevent stale authentication/rehash races. Revoked rows remain recorded; no plaintext credentials or original tokens are stored. Journal data and portable export are unaffected.

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

Task 10 adds one optional current tag to private search without changing storage. Owner-scoped EntryTag EXISTS combines with literal content/date conditions using AND, avoiding duplicate pagination rows. Historical revision tags do not match current search; deleted entries stay excluded. The search-v1 digest adds a canonical tag UUID only when present, preserving existing no-tag cursors. There is no new index, migration or search-history write.
