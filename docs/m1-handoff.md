# M1 最小安全日记：开发交接

本轮按 `tasks/01-journal.md` 实现 owner 登录与日记闭环。M0 已合入主分支；M1 的实际验证状态见 [m1-acceptance.md](m1-acceptance.md)。后续模型先检查当前分支和 PR 状态，不要重建骨架。

## 模块入口

| 路径 | 职责 |
| --- | --- |
| `apps/server/src/life_archive/auth/` | owner / session / throttle 模型、Argon2id、CSRF、请求依赖、登录路由与安全错误响应 |
| `apps/server/src/life_archive/cli.py` | `init-owner`，交互式双密码输入或显式 `--password-stdin`；绝不覆盖已有 owner |
| `apps/server/src/life_archive/journal/` | 原文和快照模型、严格 schema、原子事务服务、owner 范围的 CRUD / 分页 / 历史 |
| `apps/server/src/life_archive/main.py` | 组装路由、隐藏公开 API 文档、通用验证错误、不缓存私密 API |
| `apps/server/alembic/versions/0002_owner_sessions.py` | 唯一 owner、会话摘要、共享登录预算 |
| `apps/server/alembic/versions/0003_journal.py` | 日记、版本快照、请求去重与列表索引 |
| `apps/server/tests/auth/`、`tests/journal/` | 真实 PostgreSQL 的认证、隔离、冲突、并发与迁移测试 |
| `apps/web/src/auth/` | 会话检查、登录、退出、失效草稿隔离、会话重新验证 |
| `apps/web/src/api/` | 同源、带超时/取消与运行时响应校验的 HTTP 客户端 |
| `apps/web/src/components/MarkdownEditor.tsx` | 原文编辑器适配层、中文 composition 状态 |
| `apps/web/src/journal/` | 录入、日期、列表、编辑冲突比对、删除确认、修订历史 |
| `scripts/smoke-journal.py`、`smoke-browser.mjs` | 隔离 HTTP/重启持久化与真实 Chrome 全链路验收 |

## 必须沿用的约定

认证依赖与路由共享每请求的数据库会话。认证查询已开启事务，日记服务应显式 `commit()` / `rollback()`，不要再次嵌套 `session.begin()`。未认证的 cookie 检查先于数据库依赖；health 和匿名 401 不应要求数据库配置。

所有日记查询和更新都带 `user_id` 条件。修改和删除通过 SQL `UPDATE ... WHERE revision = expected_revision ... RETURNING` 实现原子比较；成功后在同一事务插入快照。创建先保留 revision 1，去重请求重试对比这一初始快照，不能拿后来编辑的内容误判原始请求。已删除记录重放 404，不复活。删除只做软删除、递增修订并留下最后快照；恢复和永久清除尚未提供。

owner 的 `singleton=true` CHECK + UNIQUE 同时约束唯一 owner。会话使用 256-bit 随机 token，数据库只存 SHA-256；CSRF 是由会话秘密派生的 HMAC，不能从数据库摘要还原。登录会轮换当前 cookie 会话；多个页面遇到旧的 CSRF 状态时，使用“重新验证登录”更新会话信息并保留草稿，不自动重放写入。

会话 HttpOnly / SameSite=Lax / path=/api/v1 / 绝对 7 天，默认 Secure。全局登录预算是所有用户名、来源和进程共享的 5 次/300 秒，包含成功登录；超限不会清除已有会话。此保守默认避免绕过限流，但可能暂时阻挡 owner 登录，客户端应尊重 Retry-After。

`LIFEARCHIVE_TRUSTED_ORIGINS` 是精确 Origin 的 JSON 数组，不支持通配符或路径。非 loopback 配置必须为 HTTPS 且 Secure cookie。M0 的旧 `.env` 不会被自动改写，本机 HTTP 升级时显式补入 `LIFEARCHIVE_COOKIE_SECURE=false`。生产 TLS、最小数据库角色和备份仍是后续部署任务。

原文保留换行、尾空格和用户日期；列表/历史用 React 文本节点显示，不解析任意 HTML。`entry_date` 与 UTC instant 独立。默认写作日期按 owner IANA timezone 计算，补记不会改变创建时间。

草稿、密码和 token 不写 localStorage/sessionStorage。401 会移除私密 DOM，未保存草稿仅在同一页面内存保留，重新登录相同 owner 后恢复；显式退出先确认草稿并清空。创建结果不确定时冻结原请求体和 UUID，只能重试相同请求。后续重试的 403 / 404 / 422 不能证明首次未提交，因此也不能丢弃原键；仅首次请求的明确拒绝允许修正后重新提交。没有自动后台重试或偷偷合并冲突。

## 编辑器选择与兼容边界

核验 [官方 @usememos/editor 包](https://www.npmjs.com/package/@usememos/editor) 的 `26.10.25` 版本：MIT、React/ReactDOM peer `>=18`，[官方源码](https://github.com/usememos/editor) 提供 React value/onChange API。其 [IME 验证清单](https://github.com/usememos/editor/blob/main/docs/ime-checklist.md) 要求真实系统键盘验证，未构成已完成的跨平台保证。

M1 因此使用受控原生 textarea 的独立适配层，不引入尚未完成验证的依赖，也不改变存储格式。已验证 Chrome 的 composition 事件和手机尺寸布局；仍需人工核验真实 macOS/Windows/iOS/Android 中文键盘、候选词、reconversion 和移动软键盘。后续采用第三方编辑器前固定版本、验证这些项目，再替换适配层；不能声称本轮已集成 Memos 编辑器。

## 精确运行与测试

完整启动、owner 初始化和本机开发命令见根 README。迁移始终显式执行：

```bash
docker compose up -d --build --wait
docker compose exec -T api alembic upgrade head
docker compose exec api python -m life_archive.cli init-owner --username owner --timezone Asia/Shanghai
```

第二次命令可重复，第三次仅初始化首次 owner；不要用它重置密码。自动化显式选择 `--password-stdin`，密码从私密输入或 CI 临时环境取得，不放命令参数、源码或日志。

后端单测从 `apps/server` 运行 `uv run --locked pytest`。真实 PG 测试需要 `TEST_POSTGRES_{HOST,PORT,USER,PASSWORD,DB}`，使用专门的测试数据库和角色；每项测试创建、迁移随机独立 schema，不删除或重置用户库。缺少测试配置会跳过集成测试，不能当作全量通过。格式、lint 和前端命令见 README。

完整隔离验收（只针对专门测试项目，临时密码通过私密方式导出为 `LIFEARCHIVE_SMOKE_PASSWORD`，至少 15 字符）：

```bash
export COMPOSE_PROJECT_NAME=life-archive-smoke
export WEB_PORT=18080
export LIFEARCHIVE_COOKIE_SECURE=false
export LIFEARCHIVE_TRUSTED_ORIGINS='["http://127.0.0.1:18080"]'
docker compose up -d --build --wait
bash scripts/smoke-compose.sh
printf '%s\n' "$LIFEARCHIVE_SMOKE_PASSWORD" | docker compose exec -T api \
  python -m life_archive.cli init-owner --username m1-smoke-owner --timezone Asia/Shanghai --password-stdin
python3 scripts/smoke-journal.py --base-url http://127.0.0.1:18080 --allow-test-writes --restart-postgres
node scripts/smoke-browser.mjs http://127.0.0.1:18080
docker compose down
```

Chrome 检查要求 Node 24 和本机 Chrome（可通过 `CHROME_BIN` 指定）。它使用独立临时 profile，需要空的活动日记列表，创建并软删除自己的验收记录，不使用用户 Chrome profile。可设置 `LIFEARCHIVE_BROWSER_ARTIFACT_DIR` 保存测试截图；CI 不上传私密画面。CLI 和 HTTP 脚本的 owner 名称默认为 `m1-smoke-owner`，浏览器可用 `LIFEARCHIVE_SMOKE_USERNAME` 更换。

上述流程会初始化 owner、写入测试日记和重启 PostgreSQL；不要对正式实例运行。保留测试卷与 schema 供排查，清理数据仍需明确方案和确认。

## 后续任务边界

M1 当前支持的闭环以 [API contract](api-contract.md) 为准。标签、附件、Markdown 富预览、trash/restore、密码轮换管理尚未提供，不要因设计文档列出而视为已实现。下一张明确分配的工单应先补真实键盘矩阵，或按 roadmap 切出归档/日历/搜索的小任务；不要直接启动新闻、AI、向量库、调度器或备份工程。

交给接手模型的提示词：

> 阅读 AGENTS.md、README.md、docs/m1-handoff.md、docs/m1-acceptance.md 和当前明确分配的工单。先确认分支/PR/工作区及上轮验收结果，复用现有 auth、journal、Base、迁移链和 API client。只做分配的切片，保留原始 Markdown/用户日期/修订事务/权限/CSRF/创建幂等，不重搭框架、不顺手升级依赖。新增行为要测试，运行真实 PostgreSQL 验证相关事务；交付代码、测试、文档、运行命令、迁移影响与剩余项。删除或不可逆操作先展示具体方案等待确认。
