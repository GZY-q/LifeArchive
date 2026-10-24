# Task M2 (first slice) — Private calendar and journal day views

M1's functional acceptance and CI passed. This slice builds on M1; until its PR
is merged, keep this change in a separate branch/PR targeting the M1 branch.

## Scope

- An authenticated monthly calendar with active journal counts per `entry_date`.
- An authenticated day detail containing paginated, unmodified journal Markdown.
- Responsive month navigation and day selection; default month/day uses the
  owner's configured timezone. Moving between journal and calendar preserves
  the current in-memory draft and uncertain create request.
- Reuse existing owner/session dependencies, journal pagination, and indexes;
  no new dependencies, tables, worker or migrations are required.

## API contract

- `GET /api/v1/calendar?year=YYYY&month=M` returns
  `{year,month,days:[{date:"YYYY-MM-DD",entry_count:2}]}`. `year` is 1–9999,
  `month` is 1–12. Days are ascending and sparse (only nonzero counts).
- `GET /api/v1/days/{entry_date}?limit=20&cursor=...` returns
  `{date:"YYYY-MM-DD",entries:{items:[EntryResponse],next_cursor:null}}`.
  Reuse M1's owner-scoped entry pagination with the selected date filter. Empty
  days return 200 with an empty list. Cursors cannot cross dates.
- Both endpoints require a session and return `Cache-Control: no-store`.
  Exclude soft-deleted and other owners' records. Never derive archive dates
  from `created_at` or fabricate news/digest fields.

## Out of scope

Keyword/tag search, On this day, tags/assets, restore/purge, news/AI/digests,
calendar event editing, third-party editor adoption and timezone settings UI.
Real OS/device IME validation remains an explicit manual M1 limitation.

## Acceptance

- Backdated entries and multiple entries per day appear on the chosen calendar
  date regardless of their UTC creation time. Editing dates and deleting
  records update counts on refresh.
- Validate leap years, year/month boundaries, empty days, pagination,
  unauthorized requests, owner isolation and deleted-record exclusion using
  real PostgreSQL tests.
- Browser checks exercise calendar/day navigation, preserved unsaved draft,
  backdated Markdown and mobile layout. Existing M1 smoke checks still pass.
- Deliver code, tests, documentation, exact run commands, a reviewable PR and
  recorded verification results. Do not describe the whole M2 as completed.
