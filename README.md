# LifeArchive

> Personal journal × world history × trustworthy AI memory.

LifeArchive 是一个独立实现、单用户优先、自托管、面向几十年持续保存的个人记忆系统。日常记录体验借鉴 Memos，但**不依赖 Memos 服务**；AI 采用内置固定工作流，**不依赖 Hermes**。

## 当前状态

- 已完成 M0 基础设施；M1 提供单一 owner 登录、私密会话、日记 CRUD、原文修订历史、补记日期、分页与并发冲突保护。
- M2 第一片提供月历计数和日期详情，按日记日期查看补记和同日多条记录；原文分页读取，切换视图保留当前草稿。
- M2 第二片提供归档搜索：中文/英文连续原文、日记日期范围和分页；手动提交，搜索词只放请求体。当前采用字面子串匹配，尚未验证大规模全文索引性能。
- M2 第三片提供“往年这一天”：在日历选择日期并展开，分页查看以前年份同月同日的原文；闰日严格匹配，切换日期或刷新重新读取。
- 编辑器通过独立适配层使用原生 Markdown 文本域；第三方编辑器的中文 IME / 移动端兼容验证仍需补齐。媒体、标签、新闻、AI、导出与备份尚未实现。
- 最新运行与限制见 [往年今日交接](docs/m2-on-this-day-handoff.md) 和 [验收记录](docs/m2-on-this-day-acceptance.md)；下一步按 [实施与接手计划](docs/next-steps.md) 逐片推进。月历见 [M2 第一片](docs/m2-handoff.md)；认证和日记约定见 [M1 交接](docs/m1-handoff.md)。历史检查保留在 [M1](docs/m1-acceptance.md) / [M0](docs/m0-acceptance.md) 验收记录。
- 所有设计取舍以 `docs/architecture.md`、`docs/product.md` 和 `docs/data-model.md` 为准。发生冲突时，先在 PR 中指出差异，不要静默改动核心约束。

## 目标

1. 5 秒内开始写日记：Markdown、标签、照片、补记、历史版本。
2. 每日世界新闻自动归档：全球要闻、科技/AI、自定义兴趣，带来源和版本。
3. 个人日记和世界事件围绕“日”聚合形成 Daily Capsule。
4. 日后支持可追溯的检索、年度回忆录与事件关联。
5. 即使 AI 和外部服务失效，日记仍然可以独立工作；数据始终可导出与恢复。

## 核心栈

- Web: React + Vite + TypeScript；Tailwind CSS / shadcn/ui；优先封装 `@usememos/editor`（核验兼容与许可证并锁版本）。
- API: FastAPI、Pydantic、SQLAlchemy 2、Alembic。
- Database: PostgreSQL；时间相关字段规范化；保留用户本地日期。
- Worker: 与 API 同一个 Python 代码库和镜像，不同启动命令；APScheduler 3.x 负责触发；数据库任务表负责持久化、重试和幂等。
- AI: 可更换的 LLM Adapter，结构化输出 + 服务端校验；不允许 LLM 任意 SQL / Shell 操作。
- Infra: Caddy、Docker Compose、私有媒体存储，后期 Restic 异地备份。

## 从零启动

要求 Docker Engine / Docker Desktop 与现代 Docker Compose 插件（支持 `up --wait`）；以下命令在仓库根目录执行。环境初始化脚本需要 Python 3，不会覆盖已有 `.env`，生成的密码不会打印或进入 Git。

```bash
python3 scripts/init-env.py
docker compose config --quiet
docker compose up -d --build --wait
docker compose exec -T api alembic upgrade head
docker compose exec api python -m life_archive.cli init-owner --username owner --timezone Asia/Shanghai
curl --fail http://127.0.0.1:8080/api/v1/health
```

初始化 owner 时输入并确认至少 15 字符的密码，不通过命令行参数传密码。数据库约束保证仅一名 owner，重复初始化会拒绝且不修改现有账户。打开 [本地首页](http://127.0.0.1:8080)，用刚初始化的账户登录。没有公开注册页面或 HTTP 初始化接口。

健康接口返回 `{"status":"ok"}`，只表示 API 存活；数据库就绪由 Compose 的 PostgreSQL healthcheck 检查，迁移是显式操作，不在 API 启动时运行。

`.env.example` 仅含占位值，不能直接作为有效密码使用。初始化脚本以 `0600` 权限新建 `.env`；已有文件时退出且不修改。手工配置时使用至少 16 字符随机数据库密码。修改 `WEB_PORT` 可换 Web 端口。Compose 内数据库固定使用 `postgres:5432`，不发布数据库、API 或 worker 端口；本机 API 开发时可以覆盖 `POSTGRES_HOST` / `POSTGRES_PORT`。

默认仅绑定 `127.0.0.1`，Caddy 提供 HTTP 开发入口。`.env.example` 显式配置 `LIFEARCHIVE_COOKIE_SECURE=false`，仅用于 loopback HTTP；应用默认值为 `true`。从 M0 升级且保留已有 `.env` 时，需要手动补入该配置才能在本机 HTTP 下使用会话。`LIFEARCHIVE_TRUSTED_ORIGINS` 是 JSON 数组，默认信任 `http://127.0.0.1:8080` 和 `http://127.0.0.1:5173`；修改 Web 端口时应同步更新。

非 loopback 来源必须使用 HTTPS 且启用 Secure cookie，配置不满足时会拒绝认证请求。公网 TLS 部署与备份尚未完成，不等同于生产发布。`web` 将 `/api`、`/api/*` 原样转发到 API，其他路径支持 SPA 回退。

### 生命周期与迁移

```bash
docker compose ps
docker compose logs --tail=100 api web
docker compose stop                 # 停止，保留容器和数据
docker compose start                # 启动已有容器
docker compose down                # 移除本项目容器/网络，保留数据库卷
docker compose up -d --build --wait  # 重建/启动，复用数据库卷
docker compose exec -T api alembic current
docker compose exec -T api alembic upgrade head
docker compose --profile worker run --rm --no-deps worker
```

Worker 与 API 共享后端镜像，最后一条命令仅记录“尚未配置任务”后成功退出；日记不依赖 worker 或 LLM。迁移链为 `0001_foundation` → `0002_owner_sessions` → `0003_journal`，升级可重复执行。后两条新增 owner、会话、限流、日记和修订表。不要直接回滚含日记数据的迁移；先制定备份/恢复方案。

**重置测试数据（破坏性操作，仅在确认测试卷可丢弃后手动执行）：**

```bash
# --volumes 会永久删除当前 Compose 项目的 PostgreSQL 数据卷。
# 请先核对项目名；不要用于正式数据。
docker compose down --volumes
docker compose up -d --build --wait
docker compose exec -T api alembic upgrade head
```

修改 `.env` 密码不会修改已初始化数据卷内的数据库密码。不要为解决密码问题直接删除正式数据卷；需要单独规划数据库凭据变更。

### 本机开发与检查

使用 Python 3.12、uv 0.12.17、Node 24.19.0、npm 11.17.0。`uv.lock` 和 `package-lock.json` 都已提交；安装使用锁定模式。优先使用中国大陆镜像，镜像不可达时的切换方式见 [交接文档](docs/m0-handoff.md)。

后端（一个终端）：

```bash
cd apps/server
uv sync --locked --dev
uv run --locked uvicorn life_archive.main:app --host 127.0.0.1 --port 8000 --reload
```

前端（另一个终端）：

```bash
cd apps/web
npm ci --registry=https://registry.npmmirror.com
npm run dev
```

打开 [前端开发页](http://127.0.0.1:5173)。Vite 将 `/api` 代理到 `127.0.0.1:8000`；`API_PROXY_TARGET` 可调整开发代理地址。只做前端开发时，也可用 `API_PROXY_TARGET=http://127.0.0.1:8080 npm run dev` 连接 Compose 中的 API。

健康接口可独立运行；登录和日记必须连接已迁移的真实 PostgreSQL。本机直接运行后端或 Alembic 时，设置可达的 `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`，并先运行迁移和 owner 初始化。不要为开发公开数据库公网端口。

```bash
# 仓库根目录
python3 -m unittest discover -s tests -v

# apps/server
uv run --locked pytest
uv run --locked ruff check . ../../scripts ../../tests
uv run --locked ruff format --check . ../../scripts ../../tests

# apps/web
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
```

真实 PostgreSQL 测试还需显式设置 `TEST_POSTGRES_HOST`、`TEST_POSTGRES_PORT`、`TEST_POSTGRES_USER`、`TEST_POSTGRES_PASSWORD`、`TEST_POSTGRES_DB`。密码从私密环境读取，勿写入命令历史。每项集成测试迁移一个随机独立 schema，保留便于排查；不重置应用数据库。不提供测试连接时会跳过这些测试，不能据此宣称 M1 全量通过。CI 自动启动独立 PostgreSQL 并运行全部测试。

### 隔离的完整验收

此流程使用独立项目和端口，验收脚本会迁移并重启该项目的 PostgreSQL。不要对含正式数据的实例运行。默认保留测试卷，不自动清理数据。

```bash
export COMPOSE_PROJECT_NAME=life-archive-smoke
export WEB_PORT=18080
docker compose config --quiet
docker compose up -d --build --wait
bash scripts/smoke-compose.sh
docker compose down
unset COMPOSE_PROJECT_NAME WEB_PORT
```

基础脚本检查首页和静态资源、API 代理与错误路由、重复迁移、`pgdata` 卷挂载、数据库重启前后迁移版本一致以及 worker 正常退出。

`scripts/smoke-journal.py` 与 `scripts/smoke-browser.mjs` 会写入并软删除隔离测试日记，需要明确的测试项目名和临时 owner 密码，完整执行顺序见 [往年今日交接](docs/m2-on-this-day-handoff.md)。CI 自动执行 HTTP、PostgreSQL 重启持久化、真实 Chrome 录入/冲突/修订/退出，以及月历计数、日期详情、归档搜索、往年今日、私密查询传输与跨视图草稿保留检查。

## 代码目录

```text
apps/web/         React 登录、日记、月历/往年今日、搜索、编辑器适配层与测试
apps/server/      FastAPI 认证/日记/日期聚合、SQLAlchemy、Alembic、独立 worker 与测试
infra/Caddyfile   静态 SPA 与 /api 代理
compose.yaml      web / api / postgres；worker 为可选 profile
scripts/          安全环境初始化、隔离 Compose / HTTP / Chrome 验收
tests/            环境初始化的标准库测试
.github/workflows/ci.yml
docs/             产品/架构设计、各任务验收与后续交接
tasks/            严格按顺序执行的里程碑工单
```

## 文档导航

- `AGENTS.md` — 给 Codex 的长期规则（保持短小）
- `docs/product.md` — 产品目标、功能范围、用户体验
- `docs/architecture.md` — 组件与数据流、部署原则
- `docs/data-model.md` — 数据域、关键约束和扩展策略
- `docs/api-contract.md` — V1 API 草案
- `docs/security-and-backup.md` — 隐私、安全、备份恢复
- `docs/roadmap.md` — 里程碑、验收标准
- `tasks/00-foundation.md` — 第一张可执行工单
- `tasks/01-journal.md` — 第二张可执行工单
- `tasks/02-calendar-days.md` — M2 第一片：月历和日期详情
- `tasks/03-archive-search.md` — M2 第二片：私密归档搜索
- `tasks/04-on-this-day.md` — M2 第三片：往年今日
- `docs/next-steps.md` — 依赖顺序、05–07 待分配工单与接手提示词
- `docs/decisions.md` — 核心技术决策
- `docs/m0-handoff.md` — M0 实现边界、代码入口和 M1 交接
- `docs/m0-acceptance.md` — 可复核的检查结果与运行限制
- `docs/m1-handoff.md` — 日记与认证的实现入口、运行约定和后续边界
- `docs/m1-acceptance.md` — M1 本机与 CI 验收证据
- `docs/m2-handoff.md` — 月历和日期详情的实现入口、运行与后续边界
- `docs/m2-acceptance.md` — M2 第一片的实际验收证据
- `docs/m2-search-handoff.md` — 搜索契约、实现入口与运行命令
- `docs/m2-search-acceptance.md` — 归档搜索实际验收证据
- `docs/m2-on-this-day-handoff.md` — 往年今日契约、实现入口和运行命令
- `docs/m2-on-this-day-acceptance.md` — 往年今日实际验收证据

## 免责声明

文档包含未来目标与草案，不能当作已实现功能。许可证信息与第三方依赖版本须在实际引入时核验，所有密钥必须通过运行环境配置，禁止进入 Git。
