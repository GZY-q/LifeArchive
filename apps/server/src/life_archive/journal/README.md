# Journal module · M1

`router.router` mounts at `/api/v1` and declares `/entries`. Authentication uses
the shared request session; writes commit explicitly because authentication has
already started a read transaction. Originals and snapshots commit together.

- Create accepts raw `content_md` (1–100,000 characters, nonblank), `entry_date`,
  and an optional UUID `client_request_id`. A first creation returns 201; an exact
  request replay returns the currently visible entry with 200. Replay comparison
  uses revision 1, so later edits do not invalidate the original retry. A reused
  key with different original content/date returns `idempotency_conflict` (409).
- Update accepts `expected_revision` and at least one nonnull editable field.
  An atomic conditional UPDATE plus immutable snapshot prevents lost updates;
  stale revisions return `revision_conflict` (409).
- Delete requires `?expected_revision=N`, marks the entry deleted, increments
  its revision and saves a final content snapshot. It returns 204, retains all
  records, and exposes no restore or permanent-delete operation. Deleted IDs,
  revisions and creation retries return 404; a retry cannot recreate the entry.
- Lists return `{items, next_cursor}` with `limit=20` (1–100), optional
  `entry_date=YYYY-MM-DD`, and an opaque cursor. Ordering is descending
  `(entry_date, created_at, id)`, including an ID tie-breaker. The cursor must be
  used with the original date filter. It is a continuation position, not an
  immutable database snapshot: changing a sort date can move an entry between
  pages.
- Revision lists are descending, using `?before_revision=<next_cursor>` and
  `limit=20` (1–100); their `next_cursor` is an integer or null. Every operation
  is owner scoped, and every write requires the shared CSRF dependency.

Migration `0003_journal` follows `0002_owner_sessions`. It creates only `entries`
and `entry_revisions`; it does not implement media, tags, restoration, news or AI.
Tests under `tests/journal` use the shared real-PostgreSQL fixtures, including
simultaneous creation and edits. Run with the test database configuration from
the server README: `uv run --locked pytest tests/journal`.
