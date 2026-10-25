# API contract — /api/v1

M1 已实现 health、owner 会话和最小日记闭环；M2 已分片扩展月历、日记日期详情、基础归档搜索和往年今日。下方 V1 全量资源表仍包含未来草案，未列入已实现章节的资源尚未实现。

## M1 已实现

- `GET /health`：无鉴权，200 / `{"status":"ok"}`，只报告 API 存活。
- `POST /auth/login`：JSON `{username,password}`，必须有可信 `Origin`、`Content-Type: application/json` 和 `X-LifeArchive-Request: 1`。200 返回 `{user:{id,username,timezone},csrf_token}` 并设置 HttpOnly、SameSite=Lax、path=/api/v1 的随机会话 cookie。会话绝对有效期 7 天，数据库仅保存 token 的 SHA-256。未初始化或凭据错误均为通用 401。所有用户名/来源共享每 300 秒 5 次登录尝试预算（含成功），超限 429 / `Retry-After`。
- `GET /auth/me`：同上会话响应，未认证 401；CSRF token 仅放内存，不放 localStorage。
- `POST /auth/logout`：可信 `Origin` + `X-CSRF-Token`，撤销会话并清 cookie，204。
- 所有日记接口都要求有效会话，写入还要求可信 `Origin` 和本会话的 `X-CSRF-Token`。私密 API 响应，包括错误响应，均 `Cache-Control: no-store`。
- `POST /entries`：`{content_md,entry_date,client_request_id?,tag_ids?}`。新建 201，创建重放 200。Markdown 非空、最多 100,000 字符，原文不 trim；日期严格为 `YYYY-MM-DD`。相同请求 ID 对比 revision 1 的原始内容/日期/标签 ID 集合，不同请求体 409 / `idempotency_conflict`。已软删除的请求重放 404，不复活。
- `GET /entries?limit=20&cursor=...&entry_date=...&tag_id=...`：`{items,next_cursor}`，limit 1–100；按日记日期、创建时间、ID 降序做 keyset 分页。日期和单标签过滤可选、组合为 AND，cursor 不得跨过滤条件复用；无权或不存在的 tag_id 返回空列表。
- `GET /entries/{id}`：返回 `{id,content_md,entry_date,revision,created_at,updated_at,occurred_at,occurred_timezone,tags}`，occurrence 两项当前为空；无权限、不存在或已删除均 404。
- `PATCH /entries/{id}`：`{expected_revision,content_md?,entry_date?,tag_ids?}`，至少一项修改，不能为空。原子检查修订号并更新原文/日期/标签、递增 revision、插入新快照；仅改标签同样递增。旧修订 409 / `revision_conflict`。
- `DELETE /entries/{id}?expected_revision=N`：原子修订检查后软删除，204；保留原文和历史并创建最终快照。没有永久删除/恢复接口。
- `GET /entries/{id}/revisions?limit=20&before_revision=N`：`{items,next_cursor}`，快照包含 `{revision,content_md,entry_date,changed_at,editor_id,tags}`；按 revision 降序，next_cursor 是下一页的 before_revision。创建时即保留 revision 1。
- 所有 instants 为 UTC、带时区；`entry_date` 是独立用户日历日期。格式错误 422 使用通用响应，不回显密码、原文或提交值。

## 08：日记标签

- `GET /tags?limit=100&cursor=<UUID>`：owner 范围 `{items,next_cursor}`，每项 `{id,name,created_at}`；limit 1–200，UUID 升序，next_cursor 为末项 UUID 或 null，不静默截断目录。
- `POST /tags`：`{name}`，新建 201；同 owner 同规范名称幂等返回已有标签 200。沿用会话、可信 Origin、CSRF 和 no-store。
- 名称请求长度 1–256，展示名去首尾空白并 NFC，唯一键 NFKC + casefold；规范化后均为 1–40 字符，不允许控制字符/换行/空名。
- 日记 `tag_ids` 为至多 20 个不重复 UUID：创建省略视为 `[]`，PATCH 省略保持，`[]` 清空，null 拒绝；无权/不存在统一 422，整个日记写入回滚。
- 当前/修订 `tags` 为按 UUID 升序的 `{id,name}[]`。历史保存名称快照；删除最终修订保留当时标签。标签不解析或改写 Markdown。
- 本片没有标签改名/删除、层级、归档搜索标签条件或独立的日记标签写接口。

## M2 第一片：月历与日详情

- `GET /calendar?year=YYYY&month=M`：返回 `{year,month,days:[{date,entry_count}]}`。year 为 1–9999，month 为 1–12；days 按日期升序，仅包含有记录的日期，空月为 `[]`。
- `GET /days/{entry_date}?limit=20&cursor=...`：返回 `{date,entries:{items,next_cursor}}`。日期严格为 `YYYY-MM-DD`；limit 1–100，默认 20。条目与 M1 的 EntryResponse 相同，按创建时间与 ID 降序；next_cursor 原样传回，不能跨日期使用。空日为 200 / 空 items。
- 两接口均要求有效会话、仅含当前 owner 未删除的日记，并返回 `Cache-Control: no-store`。月历计数直接按 `entry_date` 聚合，不按 UTC 创建时间重新分日。分页沿用 M1 的继续位置语义，不是数据库快照。
- 日详情只含日记原文，不输出尚未实现的新闻、摘要或事件字段；没有新的写入接口或数据库迁移。

## M2 第二片：归档搜索

- `POST /search`：只读查询，JSON `{query:"",date_from:null,date_to:null,limit:20,cursor:null}`，返回 M1 的 `{items,next_cursor}`。字段可省略，必须至少有非空关键词或一个日期边界。未知字段拒绝；关键词去首尾空白后最多 200 字符，不能含 NUL；日期严格为 `YYYY-MM-DD`，起日不晚于止日；limit 为严格整数 1–100，cursor 最多 2048 字符。
- 匹配当前 `content_md` 中的完整关键词子串，英文不区分大小写；中文无需分词。`%`、`_`、反斜杠、`/`、引号按字面匹配，不解释为通配符或 SQL。日期范围按 `entry_date`，包含两端。
- 仅返回当前 owner 未删除的条目，按 `(entry_date,created_at,id)` 降序分页。独立的版本化游标绑定 owner、规范化关键词和日期条件的摘要；跨条件、跨 owner、日记/日期接口的游标及无效格式均通用 422。游标是继续位置，不是数据快照。
- 要求有效会话、可信 Origin 与 `X-CSRF-Token`，所有响应 no-store。关键词和游标放请求体，不进 URL 或浏览器持久存储。此只读 POST 替代原先未实现的 GET 搜索草案，避免私密搜索词进入普通访问日志。
- 不写日记、修订或搜索历史，不提供全文分词、相关性排序或语义检索。当前 PostgreSQL 字面子串查询没有大数据量索引性能保证。

## M2 第三片：往年今日

- `GET /on-this-day?date=YYYY-MM-DD&limit=20&cursor=...`：返回 `{date,entries:{items,next_cursor}}`，条目复用 EntryResponse。date 可省略，按当前 UTC instant 转 owner IANA 时区取本地日期，并在响应中返回；前端及后续分页显式传该日期，避免跨午夜改变条件。
- 日期严格为 `YYYY-MM-DD`，年份 1–9999；limit 1–100，默认 20；cursor 非空且最多 2048 字符。只读 owner 未删除的当前日记，`entry_date` 年份必须小于参考年份，月日完全相同；参考年 1 返回空结果。2 月 29 日只匹配以往真正的闰日，不映射到 2 月 28 日或 3 月 1 日。
- 按 `(entry_date DESC,created_at DESC,id DESC)` keyset 分页。独立 `on-this-day-v1` 游标绑定 owner 和完整参考日期；非法、跨 owner/日期/接口游标均通用 422。修改原文/日期或软删除后的重新读取反映当前数据，不查询历史修订，不承诺跨请求快照。
- 有效会话必需，未登录 401，响应 no-store；没有写入、派生表、调度、提醒或新闻/AI 字段。前端仅展开时查询，收起/离开取消；更换日期及刷新日历重读已展开区域。

## V1 全量资源规划

This is the intended resource boundary, **not implemented endpoints**. Responses must be Pydantic typed, errors consistent, pagination stable, and permission checks applied at every record read and mutation.

| Method | Resource | Purpose |
| --- | --- | --- |
| POST | `/auth/login` | owner login |
| POST | `/auth/logout` | revoke session |
| GET | `/auth/me` | current owner |
| GET / POST | `/entries` | paginated list, create |
| GET / POST | `/tags` | private paginated catalog, idempotent name creation |
| GET / PATCH / DELETE | `/entries/{id}` | detail, edit, trash |
| GET | `/entries/{id}/revisions` | version audit |
| POST | `/entries/{id}/restore` | recover soft-deleted |
| POST / GET | `/assets` / `/assets/{id}` | upload, authorized read |
| GET | `/calendar?year=&month=` | counts by day |
| GET | `/days/{YYYY-MM-DD}` | journal + digest + events by day |
| GET | `/on-this-day?date=` | past years on the exact calendar anniversary |
| GET | `/news/events` | searchable events |
| GET | `/news/digests/{YYYY-MM-DD}` | daily digest and citations |
| GET / POST / PATCH / DELETE | `/interests` | interest preferences |
| POST | `/search` | private keyword/date search; tag filtering deferred |
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
