# API contract — /api/v1

M1 已实现 health、owner 会话和最小日记闭环；M2 已分片扩展月历、日记日期详情、基础归档搜索和往年今日。下方 V1 全量资源表仍包含未来草案，未列入已实现章节的资源尚未实现。

## M1 已实现

- `GET /health`：无鉴权，200 / `{"status":"ok"}`，只报告 API 存活。
- `POST /auth/login`：JSON `{username,password}`，必须有可信 `Origin`、`Content-Type: application/json` 和 `X-LifeArchive-Request: 1`。200 返回 `{user:{id,username,timezone},csrf_token}` 并设置 HttpOnly、SameSite=Lax、path=/api/v1 的随机会话 cookie。会话绝对有效期 7 天，数据库仅保存 token 的 SHA-256。未初始化或凭据错误均为通用 401。所有用户名/来源共享每 300 秒 5 次登录尝试预算（含成功），超限 429 / `Retry-After`。
- `GET /auth/me`：同上会话响应，未认证 401；CSRF token 仅放内存，不放 localStorage。
- `POST /auth/logout`：可信 `Origin` + `X-CSRF-Token`，撤销会话并清 cookie，204。
- `POST /auth/password`：JSON `{current_password,new_password}`；`POST /auth/sessions/revoke`：JSON `{current_password}`。两者要求有效会话、可信Origin、X-LifeArchive-Request:1、application/json和CSRF，成功200 AuthResponse+新cookie/CSRF。前者改密、后者只退出其他会话；全部旧token（含当前旧token）在同一事务撤销，当前浏览器换新token接续。
- 当前密码1–1024字符，新密码15–1024，SecretStr、不trim/归一化，拒绝新密码空白/NUL或与当前相同；无效Unicode拒绝。未知字段/格式错误通用422，新旧相同422/password_unchanged；当前密码错403/invalid_current_password，不清会话。已撤销/过期token401，CSRF/Origin403，非JSON415；不回显密码。
- 登录与这两个敏感操作共用每300秒5次预算（成功/失败都计数），在hash前持久化预留，超限429+Retry-After；失败不改密码/会话。登录与改密/撤销通过owner行锁串行，锁内刷新密码并复核会话，避免旧hash或已撤销token补建有效会话。撤销不承诺取消早先已鉴权的普通业务在飞请求。
- 所有日记接口都要求有效会话，写入还要求可信 `Origin` 和本会话的 `X-CSRF-Token`。私密 API 响应，包括错误响应，均 `Cache-Control: no-store`。
- `POST /entries`：`{content_md,entry_date,client_request_id?,tag_ids?,asset_ids?,is_pinned?}`。新建201，重放200；is_pinned严格布尔，默认false。请求ID对比revision1正文/日期/标签与资产ID集合/置顶状态，不同请求体409/idempotency_conflict，当前软删除重放404。Markdown非空最多100,000字符、不trim；日期严格YYYY-MM-DD。
- `GET /entries?limit=20&cursor=...&entry_date=...&tag_id=...&order=date`：`{items,next_cursor}`，limit1–100。默认date按日记日期/创建时间/ID降序；pinned模式置顶优先后按原日期排序。日期与单标签过滤AND，游标不能跨过滤/排序复用，未知/越权标签为空列表。
- `GET /entries/{id}`：返回 `{id,content_md,entry_date,revision,created_at,updated_at,occurred_at,occurred_timezone,tags,assets,is_pinned}`，occurrence两项当前为空；无权限、不存在或已删除均404。
- `PATCH /entries/{id}`：`{expected_revision,content_md?,entry_date?,tag_ids?,asset_ids?,is_pinned?}`，至少一项，拒绝null。共用CAS更新字段/关联、递增revision并快照；置顶为严格布尔，省略保持。旧修订409/revision_conflict。
- `DELETE /entries/{id}?expected_revision=N`：原子修订检查后软删除，204；保留原文和历史并创建删除快照，可通过回收站恢复。没有永久删除接口。
- `GET /entries/{id}/revisions?limit=20&before_revision=N`：`{items,next_cursor}`，快照包含 `{revision,content_md,entry_date,changed_at,editor_id,tags,assets,is_pinned}`；按revision降序，next_cursor是下一页before_revision，创建时即保留revision1。
- 所有 instants 为 UTC、带时区；`entry_date` 是独立用户日历日期。格式错误 422 使用通用响应，不回显密码、原文或提交值。

## 08：日记标签

- `GET /tags?limit=100&cursor=<UUID>`：owner 范围 `{items,next_cursor}`，每项 `{id,name,created_at}`；limit 1–200，UUID 升序，next_cursor 为末项 UUID 或 null，不静默截断目录。
- `POST /tags`：`{name}`，新建 201；同 owner 同规范名称幂等返回已有标签 200。沿用会话、可信 Origin、CSRF 和 no-store。
- 名称请求长度 1–256，展示名去首尾空白并 NFC，唯一键 NFKC + casefold；规范化后均为 1–40 字符，不允许控制字符/换行/空名。
- 日记 `tag_ids` 为至多 20 个不重复 UUID：创建省略视为 `[]`，PATCH 省略保持，`[]` 清空，null 拒绝；无权/不存在统一 422，整个日记写入回滚。
- 当前/修订 `tags` 为按 UUID 升序的 `{id,name}[]`。历史保存名称快照；删除最终修订保留当时标签。标签不解析或改写 Markdown。
- 没有标签改名/删除、层级或独立的日记标签写接口；归档搜索标签条件由10扩展，见下文。

## 09：回收站查看与恢复

- `GET /trash?limit=20&cursor=...`：有效会话必需，仅当前 owner 软删除记录，返回 `{items,next_cursor}`。每项包含现有 EntryResponse 字段及非空带时区 `deleted_at`；limit 1–100，cursor 最长 2048。按 `(deleted_at DESC,id DESC)` keyset，独立版本化游标绑定 owner，不可与其他接口游标混用。分页是继续位置，不是跨请求快照。
- `POST /entries/{id}/restore`：可信 Origin + CSRF，JSON `{expected_revision:N}`，N 为严格正整数，拒绝未知字段。成功 200 返回活动 EntryResponse；owner、软删除状态和 revision 原子匹配后清除 deleted_at、更新 UTC updated_at、revision +1，并在同事务保存正文/日期/标签快照。
- 不存在/其他 owner 404；已恢复或 revision 不符 409 / `revision_conflict`。重复恢复不另建修订，旧请求不能恢复后来再次删除的版本。写入响应丢失时先刷新核对，不自动重试为成功。
- 恢复保留 id、创建时间、创建请求 UUID、原文、日记日期、occurred_*、标签和全部历史；现有列表、月历、日期、搜索、往年今日和默认导出重新包含该记录。导出仍为 v2，不增加迁移。
- 软删除期间普通读取/编辑/历史和创建 UUID 重放仍为 404；恢复后历史可读，原请求匹配 revision 1 时重放返回同一 id。回收站不另提供已删除历史接口，恢复后可查看。
- 所有响应包括错误均 no-store，未登录 401；无永久删除、自动清空或批量恢复。

## 11：私密图片附件

- `POST /assets`：原始二进制body，Content-Type为image/jpeg、image/png或image/webp且须与检测内容一致；需要会话、可信Origin、X-LifeArchive-Request:1与CSRF。不接收文件名/路径，不使用multipart。新上传201，同owner相同原字节SHA-256幂等返回已有200。
- 响应 `{id,mime_type,byte_size,sha256,width,height,created_at}`。静态图片最多5MiB、20,000,000像素、单边20,000；拒绝动画/损坏/截断/类型不符，格式问题422、字节或配额超限413。默认owner已登记原文件配额1GiB；没有自动删除或GC。
- `GET /assets/{id}`：仅资产owner可读，包括未关联草稿与历史/回收站图片；未登录401、未知/越权404。返回完整原始字节，正确Content-Type、nosniff、安全生成inline文件名与no-store；文件缺失/校验失败通用503，不显示服务器路径。没有匿名静态资源映射。
- POST/PATCH `/entries` 新增 `asset_ids`（最多10个不同UUID）：创建省略[]，PATCH省略保持、[]解除当前关联、null拒绝；无权或不存在统一422。与正文/日期/标签共用revision CAS与同一事务，附件变化也创建修订；创建请求重放比较revision1资产ID集合。正文仍须非空，不自动插入Markdown图片语法。
- EntryResponse及RevisionResponse新增 `assets`，为按UUID升序的完整公开资产元数据；回收站继承该字段。修订保存不可变元数据快照。解除当前关联、软删除或恢复不会删除原文件；历史仍可读取。原图字节与EXIF保留，不转码。
- 迁移0005_private_images，私有本地卷存原文件，导出v3包含所选当前/历史引用原图。详见 [图片交接](private-images-handoff.md) 与 [导出格式](export-format.md)。

## 12：日记置顶

- 现有PATCH提交 `{expected_revision,is_pinned:true|false}`，只改置顶也增加修订/UTC updated_at，并保存正文、日期、标签、图片和置顶快照。不改entry_date/created_at，不另建pin接口；删除保留状态，恢复后仍置顶。
- 日记主列表显式 `order=pinned`，按 `(is_pinned DESC,entry_date DESC,created_at DESC,id DESC)`。置顶组内仍按日记日期，不按置顶操作时间；没有拖拽或自定义顺序。API默认order=date，日详情/搜索/往年今日/回收站沿用原排序。
- 日记游标增加filter_order与位置is_pinned，缺省date/false兼容旧日期游标；pinned/date不能互换。置顶变化可跨页移动记录，分页不是快照，变更后刷新首屏。
- 前端置顶写入使用全局busy保护，正在编辑同篇时禁用卡片动作；成功刷新列表、不重挂编辑器。冲突或不确定结果提示刷新核对，不覆盖未保存草稿/图片/冻结UUID/409面板。
- 0006_journal_pinning为当前/历史增加is_pinned，旧记录false；导出v4增加当前/历史同名字段，原图/清单约定不变。

## 13：账户安全界面

“账户”提供改密和退出其他会话，提交结束/离开清空密码字段，应用不记录密码日志、不写URL或持久存储。写入期间全局busy阻止重复动作/导航/退出。成功将新Session交同owner认证边界，不重挂日记，草稿/图片/冻结UUID/409保留，后续写入用新CSRF。403当前密码错只提示重输；401沿用重新登录与草稿保留。

网络结果不确定不显示成功、不自动重试；敏感表单跨导航保持锁定，先重新验证登录或用新密码重登核对，再允许提交。无公开找回、邮件、重置后门或设备会话列表；无新表/迁移/配置/依赖，head0006、导出v4不变。

## 14：安全Markdown预览（无API变更）

预览完全在前端派生，不读取/写入新接口、不创建修订或改写content_md；原文默认可见、独立切换，现有MarkdownEditor一直挂载。CommonMark/GFM只读渲染，原始HTML忽略、代码不执行；绝对http/https且无凭据/控制字符的链接才可点击，新页noopener/noreferrer/no-referrer。其他URL降纯文本，Markdown图片只显示alt占位，不读取src，私密图片继续AssetGallery鉴权懒加载。

预览不进入请求体、数据库或导出，head0006/格式v4不变；冻结创建UUID、401/密码轮换和409草稿边界沿用。不是富文本编辑器或HTML清洗接口；真实IME矩阵仍以07人工证据为准。

## M2 第一片：月历与日详情

- `GET /calendar?year=YYYY&month=M`：返回 `{year,month,days:[{date,entry_count}]}`。year 为 1–9999，month 为 1–12；days 按日期升序，仅包含有记录的日期，空月为 `[]`。
- `GET /days/{entry_date}?limit=20&cursor=...`：返回 `{date,entries:{items,next_cursor}}`。日期严格为 `YYYY-MM-DD`；limit 1–100，默认 20。条目与 M1 的 EntryResponse 相同，按创建时间与 ID 降序；next_cursor 原样传回，不能跨日期使用。空日为 200 / 空 items。
- 两接口均要求有效会话、仅含当前 owner 未删除的日记，并返回 `Cache-Control: no-store`。月历计数直接按 `entry_date` 聚合，不按 UTC 创建时间重新分日。分页沿用 M1 的继续位置语义，不是数据库快照。
- 日详情只含日记原文，不输出尚未实现的新闻、摘要或事件字段；没有新的写入接口或数据库迁移。

## M2 第二片：归档搜索

- `POST /search`：只读查询，JSON `{query:"",date_from:null,date_to:null,tag_id:null,limit:20,cursor:null}`，返回 M1 的 `{items,next_cursor}`。字段可省略，必须至少有非空关键词、一个日期边界或单个标签。tag_id 为可选 UUID（省略/null等价）；未知字段拒绝。关键词去首尾空白后最多 200 字符，不能含 NUL；日期严格为 `YYYY-MM-DD`，起日不晚于止日；limit 为严格整数 1–100，cursor 最多 2048 字符。
- 匹配当前 `content_md` 中的完整关键词子串，英文不区分大小写；中文无需分词。`%`、`_`、反斜杠、`/`、引号按字面匹配，不解释为通配符或 SQL。日期范围按 `entry_date`，包含两端。
- 仅返回当前 owner 未删除的条目，按 `(entry_date,created_at,id)` 降序分页。独立 `search-v1` 游标绑定 owner、规范化关键词、日期及非空标签的摘要；跨条件、跨 owner、其他接口游标及无效格式均通用 422。tag_id 省略/null时沿用旧摘要，旧无标签游标仍兼容；增加/移除/更换标签须重新搜索。游标是继续位置，不是数据快照。
- 要求有效会话、可信 Origin 与 `X-CSRF-Token`，所有响应 no-store。关键词、日期、标签和游标放请求体，不进 URL 或浏览器持久存储。此只读 POST 替代原先未实现的 GET 搜索草案，避免私密搜索词进入普通访问日志。
- 不写日记、修订或搜索历史，不提供全文分词、相关性排序或语义检索。当前 PostgreSQL 字面子串查询没有大数据量索引性能保证。

### 10：归档标签条件

单标签、关键词与日期为 AND；可以仅提交 tag_id。通过 owner 范围的当前 EntryTag EXISTS 过滤，不关联历史修订标签，不因多标签产生重复结果。未知/其他 owner 标签统一200空结果；无效 UUID 通用422。移除标签、软删除或恢复后的重新搜索反映当前状态。

前端复用现有分页标签目录；加载失败独立重试，不阻塞无需标签的查询。选择标签只改表单，显式搜索才生成新的已提交条件；结果摘要、翻页和重试使用提交时标签，不受随后输入变化影响。切换视图保留内存表单，显式退出清空。没有新迁移、依赖或导出版本变化。

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
| POST | `/auth/password` | verify current password, change and rotate all sessions |
| POST | `/auth/sessions/revoke` | verify current password, replace all sessions with this browser's new session |
| GET | `/auth/me` | current owner |
| GET / POST | `/entries` | paginated list, create |
| GET / POST | `/tags` | private paginated catalog, idempotent name creation |
| GET / PATCH / DELETE | `/entries/{id}` | detail, edit, trash |
| GET | `/entries/{id}/revisions` | version audit |
| POST | `/entries/{id}/restore` | recover soft-deleted |
| GET | `/trash` | private paginated deleted journal entries |
| POST / GET | `/assets` / `/assets/{id}` | upload, authorized read |
| GET | `/calendar?year=&month=` | counts by day |
| GET | `/days/{YYYY-MM-DD}` | journal + digest + events by day |
| GET | `/on-this-day?date=` | past years on the exact calendar anniversary |
| GET | `/news/events` | searchable events |
| GET | `/news/digests/{YYYY-MM-DD}` | daily digest and citations |
| GET / POST / PATCH / DELETE | `/interests` | interest preferences |
| POST | `/search` | private keyword/date/tag search with AND filters |
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
