# Task M2 (second slice) — Private journal archive search

Build on accepted calendar/day-view checks. Until PR #3 is merged, target its
branch `codex/m2-calendar-days` from a separate branch and PR.

## Scope and contract

- Enable the authenticated “归档” view with an explicitly submitted keyword and
  optional inclusive `entry_date` range, paginated original Markdown results,
  loading/empty/error/retry states and safe navigation back to the journal.
- `POST /api/v1/search` is read-only and returns M1's `{items,next_cursor}`.
  Body: `{query:"",date_from:null,date_to:null,limit:20,cursor:null}`. All fields
  are optional with those defaults; require a nonblank query or at least one
  date bound. Strip query edge whitespace, cap at 200 characters, reject NUL.
  Dates must be YYYY-MM-DD in years 1–9999 and date_from <= date_to. Limit 1–100
  (strict integer), cursor <=2048 characters, reject unknown fields.
- Match the whole query as a literal case-insensitive substring of current
  `content_md`: Chinese works without segmentation; `%`, `_`, `/`, backslash
  and quotes are literal text, not SQL wildcards or commands. No regex,
  relevance ranking or semantic search.
- Require the existing session, trusted Origin and CSRF dependency; return
  no-store. Query terms belong in the JSON body, never URL, local/session
  storage, analytics or logs. This intentionally replaces the unimplemented
  GET /search draft to avoid journal words in access logs/browser history.
- Owner + active-entry filtering always applies. Sort by
  `(entry_date DESC,created_at DESC,id DESC)` and use keyset pagination.
  A versioned cursor binds owner and the normalized query/date filters using
  a digest, and contains no raw search query. Reject malformed/cross-filter
  cursors with a generic 422; do not reuse journal/day cursors.
- No data/schema/lockfile changes. PostgreSQL substring matching is the small
  archive baseline, not an indexed full-text search performance guarantee.

## UI boundaries

- Submit searches explicitly; do not issue one request per keystroke. Result
  filters reflect the submitted request, even when inputs are edited later.
- Cancel/ignore stale results and pagination when submitting a new search or
  leaving the view. Preserve the journal component and its in-memory draft,
  uncertain creation ID and conflict state; navigation is disabled during
  journal writes. 401 removes every private view; logout clears search state.
- Render Markdown as text. Native date inputs, clear labels and responsive
  layout. No rich preview, automatic journal edits, query URL or persistence.

## Acceptance

- Real PostgreSQL tests cover Chinese/English, literal wildcard characters,
  injection-like text, inclusive dates/backdating, owner/deleted exclusion,
  edited originals, pagination/ties and invalid/cross-filter cursors.
- Auth/CSRF/Origin and invalid payloads do not leak query content. Searching
  does not mutate entries, revisions or original Markdown.
- Frontend tests cover submit-only behavior, filter snapshot, pagination,
  request races, error retry, 401, draft preservation and safe raw rendering.
- Existing M1/M2 checks pass; extend HTTP and Chrome smoke for search and
  mobile layout. Deliver code/tests/docs/run instructions/PR with evidence.
- Plan later tasks in docs/next-steps.md; do not implement On this day, export,
  restore, tags/assets, news/AI, pg_trgm or a new service in this slice.
