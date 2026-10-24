# M1 验收记录

验证日期：2026-10-24（Asia/Shanghai）。范围为 `tasks/01-journal.md` 的最小安全日记闭环。

## 本机检查

使用 Python 3.12.14 / uv 0.12.17 / Node 24.19.0 / npm 11.17.0，真实 PostgreSQL 17.11。测试库与预览库在独立新建 cluster 中，仅监听 loopback 25432，密码放仓库外 0600 文件；不使用系统默认数据库实例，不改写已有 `.env`。

| 命令 / 检查 | 结果 |
| --- | --- |
| 根目录：`python3 -m unittest discover -s tests -v` | 4 项环境初始化保护测试 |
| `apps/server`：设置 TEST_POSTGRES_* 后 `uv run --locked pytest -q` | 78 项通过，真实 PostgreSQL，零跳过 |
| `apps/server`：`uv run --locked ruff check . ../../scripts ../../tests` | 通过 |
| `apps/server`：`uv run --locked ruff format --check . ../../scripts ../../tests` | 通过 |
| `apps/server`：`uv lock --check --offline` | 40 个解析包，锁一致 |
| `apps/web`：`npm run lint`、`npm run format:check`、`npm run typecheck` | 通过 |
| `apps/web`：`npm test` | 27 项通过 |
| `apps/web`：`npm run build` | 通过 |
| Compose standalone v5.6.1：`compose --profile worker config --quiet` | 配置通过；本机仍没有 Docker Engine |
| `GOPROXY=https://goproxy.cn,direct go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.12 -shellcheck='' .github/workflows/ci.yml` | 通过；未宣称运行 ShellCheck |
| `git diff --check` | 通过 |

不重复计数：78 后端 + 27 前端 + 4 环境保护 = **109 项测试**。真实 PG 测试涵盖 owner 唯一性、密码/CLI、会话摘要/过期/撤销、CSRF/Origin、共享并发限流、数据权限、Markdown 往返、日期、创建并发去重、原子修订和删除竞争、迁移/metadata 一致性。前端回归包含未确认创建在后续 403 / 404 / 422 后继续沿用原请求键，避免响应丢失后重复建档。

## 实际链路

已将独立预览库迁移至 `0003_journal`，使用 CLI 初始化一个临时本机 owner。账号密码仅放仓库外 0600 文件，不进入 Git、截图或日志。

`scripts/smoke-journal.py` 对原生 Caddy → Uvicorn → PostgreSQL 通过：匿名读取 401，登录与 HttpOnly cookie，缺失 CSRF 和外部 Origin 拒绝，中文 Markdown / 尾空格 / 换行往返，补记日期，同日多条，创建请求去重，编辑历史，旧版本 409，分页，软删除不复活，退出后旧 token 失效。

`scripts/smoke-browser.mjs` 在真实 Chrome 执行 React 与 API：登录、CDP IME composition、原文保存、补记、轮换会话后 403 保留草稿并重新验证、多页面模拟写入后 409 保留草稿、读取新版并显式继续、展示三个历史快照、删除确认和退出后清空私密 DOM。桌面 1440×1000 与手机尺寸 390×844 无水平溢出，测试截图已检查，HTML 内容只显示文本而未执行。localStorage / sessionStorage 为空。

Chrome composition 与手机尺寸模拟不能替代所有真实系统中文键盘和软键盘验收。`@usememos/editor` 未引入；编辑器选择与未完成矩阵见交接文档，不能声称完成第三方编辑器集成。

## 容器验收

本机无 Docker Engine；容器门禁已在 [PR #2](https://github.com/GZY-q/LifeArchive/pull/2) 的 [CI run 40097908622](https://github.com/GZY-q/LifeArchive/actions/runs/40097908622) 全部通过。对应功能提交为 [`25b885e`](https://github.com/GZY-q/LifeArchive/commit/25b885e9a4e063aebd813e9fc687027098dd4f61)。

| CI job | 结果 |
| --- | --- |
| [backend](https://github.com/GZY-q/LifeArchive/actions/runs/40097908622/job/120883916998) | 78 项真实 PG 测试、4 项环境保护测试、Ruff 通过，零跳过 |
| [frontend](https://github.com/GZY-q/LifeArchive/actions/runs/40097908622/job/120883916840) | lint、格式、类型、27 项测试与构建通过 |
| [compose](https://github.com/GZY-q/LifeArchive/actions/runs/40097908622/job/120884040541) | 镜像构建、Caddy 路由、重复迁移、worker 独立退出、HTTP 与 Chrome 全部通过 |

Compose 实测 PostgreSQL 重启后，owner 会话和已编辑日记的修订/内容仍保留；Chrome 随后完成会话轮换恢复、IME、补记、冲突处理、历史、删除和退出。容器检查没有依赖 worker 或 LLM。CI 停止容器时保留测试数据卷，未执行破坏性回滚。

## 迁移与交付限制

- `0002_owner_sessions` 新增 users/sessions/login_throttle，`0003_journal` 新增 entries/entry_revisions；没有修改已应用的 `0001_foundation`。
- 升级是添加表，不删除旧数据。回滚 M1 迁移会删除新增表，必须先制定备份/恢复方案并获确认，本轮没有执行回滚或删卷。
- M1 日记无需 worker / LLM；图片、标签、日历、新闻、AI、导出和备份尚未实现。
- 本机测试使用 Homebrew 安装 PostgreSQL 17；Homebrew 同时更新了 ca-certificates 并将 openssl 命令链接切换为 OpenSSL 4，OpenSSL 3 的原安装仍保留。没有启用 brew services。
