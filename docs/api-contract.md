# API contract draft — /api/v1

M0 唯一已实现的接口为 `GET /api/v1/health`，HTTP 200 / `{"status":"ok"}`，无鉴权、无敏感信息，只报告 API 存活，不检查数据库。下表仍是未来接口草案。

This is the intended resource boundary, **not implemented endpoints**. Responses must be Pydantic typed, errors consistent, pagination stable, and permission checks applied at every record read and mutation.

| Method | Resource | Purpose |
| --- | --- | --- |
| POST | `/auth/login` | owner login |
| POST | `/auth/logout` | revoke session |
| GET | `/auth/me` | current owner |
| GET / POST | `/entries` | paginated list, create |
| GET / PATCH / DELETE | `/entries/{id}` | detail, edit, trash |
| GET | `/entries/{id}/revisions` | version audit |
| POST | `/entries/{id}/restore` | recover soft-deleted |
| POST / GET | `/assets` / `/assets/{id}` | upload, authorized read |
| GET | `/calendar?year=&month=` | counts by day |
| GET | `/days/{YYYY-MM-DD}` | journal + digest + events by day |
| GET | `/news/events` | searchable events |
| GET | `/news/digests/{YYYY-MM-DD}` | daily digest and citations |
| GET / POST / PATCH / DELETE | `/interests` | interest preferences |
| GET | `/search` | keyword/date/tag search |
| GET | `/jobs` | admin task status |
| POST | `/jobs/{id}/retry` | authenticated manual re-run |
| POST | `/exports` | start export |

## Essential behavior

- Use secure HttpOnly cookie sessions, CSRF protection for state-changing cookie-authenticated requests, and conservative CORS policy.
- POST `/entries` should accept an optional `client_request_id` for retry deduplication.
- PATCH entry should carry expected revision; conflicts return HTTP 409.
- `GET /days/{date}` must not invent causality or overwrite original journal content. Date is interpreted using owner's configured archive timezone unless request contract explicitly overrides it.
- Source article IDs and digest status must be verifiable and traceable.
- No public AI endpoints that can execute arbitrary tools or queries.
