# API contract — /api/v1

M1 已实现 health、owner 会话和最小日记闭环。下方 V1 全量资源表仍包含未来草案，未列入本节的资源尚未实现。

## M1 已实现

- `GET /health`：无鉴权，200 / `{"status":"ok"}`，只报告 API 存活。
- `POST /auth/login`：JSON `{username,password}`，必须有可信 `Origin`、`Content-Type: application/json` 和 `X-LifeArchive-Request: 1`。200 返回 `{user:{id,username,timezone},csrf_token}` 并设置 HttpOnly、SameSite=Lax、path=/api/v1 的随机会话 cookie。会话绝对有效期 7 天，数据库仅保存 token 的 SHA-256。未初始化或凭据错误均为通用 401。所有用户名/来源共享每 300 秒 5 次登录尝试预算（含成功），超限 429 / `Retry-After`。
- `GET /auth/me`：同上会话响应，未认证 401；CSRF token 仅放内存，不放 localStorage。
- `POST /auth/logout`：可信 `Origin` + `X-CSRF-Token`，撤销会话并清 cookie，204。
- 所有日记接口都要求有效会话，写入还要求可信 `Origin` 和本会话的 `X-CSRF-Token`。私密 API 响应，包括错误响应，均 `Cache-Control: no-store`。
- `POST /entries`：`{content_md,entry_date,client_request_id?}`。新建 201，创建重放 200。Markdown 非空、最多 100,000 字符，原文不 trim；日期严格为 `YYYY-MM-DD`。相同请求 ID 对比 revision 1 的原始内容/日期，不同请求体 409 / `idempotency_conflict`。已软删除的请求重放 404，不复活。
- `GET /entries?limit=20&cursor=...&entry_date=...`：`{items,next_cursor}`，limit 1–100；按日记日期、创建时间、ID 降序做 keyset 分页。日期过滤可选，cursor 不得跨日期过滤复用。
- `GET /entries/{id}`：返回 `{id,content_md,entry_date,revision,created_at,updated_at,occurred_at,occurred_timezone}`，最后两项当前为空；无权限、不存在或已删除均 404。
- `PATCH /entries/{id}`：`{expected_revision,content_md?,entry_date?}`，至少一项修改，不能为空。原子检查修订号并更新原文、递增 revision、插入新快照；旧修订 409 / `revision_conflict`。
- `DELETE /entries/{id}?expected_revision=N`：原子修订检查后软删除，204；保留原文和历史并创建最终快照。没有永久删除/恢复接口。
- `GET /entries/{id}/revisions?limit=20&before_revision=N`：`{items,next_cursor}`，快照包含 `{revision,content_md,entry_date,changed_at,editor_id}`；按 revision 降序，next_cursor 是下一页的 before_revision。创建时即保留 revision 1。
- 所有 instants 为 UTC、带时区；`entry_date` 是独立用户日历日期。格式错误 422 使用通用响应，不回显密码、原文或提交值。

## V1 全量资源规划

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
