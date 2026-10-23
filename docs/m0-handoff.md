# M0 开发交接

本文件面向后续接手开发者与模型。先读 `AGENTS.md`、`README.md`、产品/架构/数据模型文档和当前工单。实现状态与设计草案应分开理解，实际验收记录见 [m0-acceptance.md](m0-acceptance.md)。

## 已建立的边界

| 路径 | 职责与扩展方式 |
| --- | --- |
| `apps/web/src/App.tsx`、`styles.css` | 品牌首页、响应式布局、禁用的未来导航。M0 没有业务路由或编辑器。 |
| `apps/web/src/api/health.ts` | 唯一 HTTP 请求，校验状态码和响应结构，使用同源 `/api/v1/health`。 |
| `apps/web/src/components/HealthIndicator.tsx` | 加载/成功/失败、手动重试、8 秒超时和卸载取消；不后台轮询。 |
| `apps/server/src/life_archive/main.py` | 应用工厂和类型化 health；不启动数据库迁移、调度器或 worker。 |
| `apps/server/src/life_archive/settings.py` | 运行设置和单独的数据库设置；懒加载密码，SecretStr，SQLAlchemy URL.create 处理特殊字符。 |
| `apps/server/src/life_archive/db.py` | 懒加载同步 engine/sessionmaker、Base 命名约定、请求作用域会话；PostgreSQL 会话时区 UTC。 |
| `apps/server/alembic/` | `0001_foundation` 无业务表基线，仅产生 Alembic 版本记录。新增 ORM 模型后，须在 `env.py` 中导入模型模块，使其注册到 `Base.metadata`，再自动生成迁移。 |
| `apps/server/src/life_archive/worker.py` | 独立入口，说明无任务后退出；只有未来对应任务才引入调度/持久任务表。 |
| `compose.yaml`、`infra/Caddyfile` | 同源 SPA/API；DB 内部网络和命名卷；API/worker 同镜像；worker profile 默认关闭。 |
| `scripts/init-env.py` | 独占新建 `.env`，生成随机密码、权限 `0600`；已有配置绝不覆盖。 |
| `scripts/smoke-compose.sh` | 已启动的隔离测试项目上验证代理、迁移和重启持久化；不会删除数据卷。 |
| `.github/workflows/ci.yml` | 前后端检查后执行真实 Compose 验收，临时密码不进入源码。 |

未来数据库服务必须显式使用 `session.begin()` 或 `session.commit()`；依赖退出只关闭会话，未提交事务会回滚。不要在会话依赖里自动提交，也不要在 API import/startup 中 `create_all()` 或执行迁移。当前同步 SQLAlchemy 应配合 FastAPI 同步处理函数，避免在 async handler 中阻塞事件循环。

后端本机命令从 `apps/server` 执行，设置读取 `../../.env`，环境变量优先；容器只使用 Compose 注入的环境。`Settings` 与 `DatabaseSettings`/engine 有缓存，变更运行配置需重启进程。API health 不会创建连接或读取数据库密码；HTTP 200 只表示 API 存活。

## 技术默认值与依赖更新

- Python 3.12.14 / uv 0.12.17；Node 24.19.0 / npm 11.17.0。直接依赖精确版本、传递依赖锁文件；不要仅改 manifest 而不更新 lock。
- npm 默认使用 npmmirror，`.npmrc` 的 `replace-registry-host=always` 允许安装锁文件时切换 registry：`npm ci --registry=https://registry.npmjs.org`。Compose 构建可设置 `NPM_REGISTRY=https://registry.npmjs.org`。
- uv 默认使用清华镜像，源地址属于锁文件内容；不能承诺在 `--locked` 安装时任意换源。镜像长期不可用时，在独立改动中将 `pyproject.toml` 的 index URL 改为 `https://pypi.org/simple`，执行 `uv lock`、检查锁差异，再 `uv sync --locked` 和运行全套检查。不要把临时凭据写入 index URL。
- React + 纯 CSS 满足 M0；没有引入 Tailwind/shadcn 或第三方编辑器。TypeScript 版本须符合 `typescript-eslint` 的 peer 范围，升级时一起检查。
- PostgreSQL 17.11、Caddy 2.11.7，镜像使用具体版本标签；没有锁到 digest，基础镜像安全更新仍需单独验证。
- Caddy 使用互斥 `handle`，API 路由保留 `/api` 前缀且不能回退成 HTML；前端开发由 Vite 代理同一前缀，不需要宽松 CORS。
- API 无公开 Swagger/OpenAPI 页面，M0 仅 health 一条路由；没有私密业务或静态媒体入口。

## 迁移与运行限制

`alembic upgrade head` 是部署后的显式命令。基线不建 `users`、`entries`、`jobs` 等未来业务表，回滚基线不会删除业务数据，但回滚或删除有数据的未来迁移仍须先给出方案并获确认。M0 不提供自动数据重置入口，README 的 `down --volumes` 仅为手工确认后的测试清理指令。

默认容器端口只发布 `127.0.0.1:8080`。这是一套本机开发基础设施，不是完成认证、TLS、私有媒体保护和备份的生产部署。当前 PostgreSQL 初始化用户也是数据库所有者；生产最小权限角色分离应随部署加固另行设计，不要把无认证 M0 暴露到公网。

单元测试中 SQLite 只验证 SQLAlchemy 提交/回滚/关闭语义；离线 Alembic 测试只验证生成的 PostgreSQL SQL。它们都不能代替真实 PostgreSQL 的迁移和持久化验收。测试卷保留至用户明确决定清理；任何容器失败首先查日志，不要用删卷作为通用修复。

## 下一张工单：M1 的第一片

先确认 M0 验收记录和 CI，审查本 PR，再执行 `tasks/01-journal.md`。为控制后续模型的上下文，可拆成依赖明确的小 PR：

1. 单一 owner 初始化、密码哈希、私密会话、CSRF 和记录权限边界；没有公开注册。
2. `users` / `entries` / `entry_revisions` 的模型、迁移、服务和 API；原始 Markdown 往返不变，事务内创建修订，409 乐观冲突，客户端创建幂等。
3. 编辑器适配层、最小录入/列表界面；引入 `@usememos/editor` 前核验实际 API、许可证、锁定版本、React/中文 IME/移动端兼容。先完成工单内最小闭环，不扩展到图片或新闻。

每个切片都补行为测试，使用现有 `Base`、会话和健康接口约定。日记 `entry_date` 为用户日期，UTC instants 用带时区时间戳；原文与修订不得被 AI 派生内容替换。无 worker、无外部 AI 时，M1 日记必须可用。不要在 M1 顺手加入新闻、AI、RAG、定时任务、队列、备份或额外微服务。

可交给接手模型的开场指令：

> 阅读 AGENTS.md、README.md、docs/m0-handoff.md、docs/m0-acceptance.md 和 tasks/01-journal.md，先确认 M0 验收通过。检查当前分支与未提交修改，选择当前明确分配的 M1 切片，列短计划后实现；沿用现有模块、锁文件和迁移方式。不要超范围，不要重建项目骨架。提交代码、行为测试、运行命令、迁移影响和剩余项，删除或不可逆操作先给出方案等待确认。

## 已核验的上游参考

- [Caddy SPA 与 API 路由示例](https://caddyserver.com/docs/caddyfile/patterns/)
- [Docker Compose 网络](https://docs.docker.com/reference/compose-file/networks/) 与 [profiles](https://docs.docker.com/compose/how-tos/profiles/)
- [SQLAlchemy URL.create](https://docs.sqlalchemy.org/en/20/core/engines.html#creating-urls-programmatically)、[Session](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)、[uv Docker](https://docs.astral.sh/uv/guides/integration/docker/)
- [npm replace-registry-host](https://docs.npmjs.com/cli/v11/using-npm/config/#replace-registry-host)
