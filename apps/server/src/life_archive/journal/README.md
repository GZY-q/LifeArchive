# Journal module · M1

`router.router`, `tag_router.router`, and `trash_router.router` mount at `/api/v1` for `/entries`, `/tags`, and `/trash`. Authentication uses
the shared request session; writes commit explicitly because authentication has
already started a read transaction. Originals and snapshots commit together.

- Create accepts raw `content_md` (1–100,000 characters, nonblank), `entry_date`,
  optional UUID `client_request_id`, and up to 20 distinct owner `tag_ids` (default `[]`). A first creation returns 201; an exact
  request replay returns the currently visible entry with 200. Replay comparison
  uses revision 1, so later edits do not invalidate the original retry. A reused
  key with different original content/date/tag-ID set returns `idempotency_conflict` (409).
- Update accepts `expected_revision` and at least one nonnull editable field.
  An atomic conditional UPDATE plus immutable snapshot prevents lost updates;
  stale revisions return `revision_conflict` (409). Omitted `tag_ids` preserves
  associations, `[]` clears them, and null is rejected. Association replacement
  happens after the successful revision CAS in the same transaction. Tag-only
  changes also create a revision; each snapshot stores `{id,name}` labels.
- Delete requires `?expected_revision=N`, marks the entry deleted, increments
  its revision and saves a final content snapshot. It returns 204, retains all
  records. Deleted IDs, revisions and creation retries return 404 until explicitly
  restored; a creation retry cannot restore the entry. There is no permanent-delete operation.
- Lists return `{items, next_cursor}` with `limit=20` (1–100), optional
  `entry_date=YYYY-MM-DD`, optional `tag_id=<UUID>` (combined with date using AND),
  and an opaque cursor. Ordering is descending
  `(entry_date, created_at, id)`, including an ID tie-breaker. The cursor must be
  used with the original date and tag filters. It is a continuation position, not an
  immutable database snapshot: changing a sort date can move an entry between
  pages.
- Revision lists are descending, using `?before_revision=<next_cursor>` and
  `limit=20` (1–100); their `next_cursor` is an integer or null. Every operation
  is owner scoped, and every write requires the shared CSRF dependency.

- Tags: `GET /tags?limit=100&cursor=<UUID>` returns `{items,next_cursor}` ordered
  by UUID, with limit 1–200. `POST /tags {name}` returns 201, or the existing
  normalized-name match with 200. Names use trimmed NFC for display and
  NFKC+casefold for uniqueness; both normalized lengths are 1–40. Control
  characters and line breaks are rejected. Tags have no rename/delete endpoint.
- Entry and revision responses include `tags: [{id,name}]`, ordered by UUID.
  Current associations have database-enforced owner consistency. Unknown and
  unauthorized tag IDs receive the same generic 422 response on writes.
- Trash: `GET /trash` lists deleted entries plus `deleted_at`, ordered by deletion
  instant and ID descending, with a separate owner-bound `trash-v1` cursor.
  `POST /entries/{id}/restore {expected_revision}` checks owner/deleted state/revision
  atomically, clears deletion, increments revision, and saves the same original/date/tags
  as a new immutable snapshot. Unknown IDs return 404; stale or already-restored IDs
  return 409. Restore preserves creation UUID, ID and all history; no new entry is created.

Migration `0004_entry_tags` follows `0003_journal`. It adds `tags`, `entry_tags`
and revision JSONB label snapshots (existing revisions receive `[]`). It does
not implement media, news or AI. Task 09 adds restoration without a new migration.
Tests under `tests/journal` use the shared real-PostgreSQL fixtures, including
simultaneous creation and edits. Run with the test database configuration from
the server README. For the focused tag checks:
`uv run --locked pytest tests/journal/test_tags.py tests/journal/test_migrations.py`.
