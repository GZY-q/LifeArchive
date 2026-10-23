# LifeArchive

> Personal journal × world history × trustworthy AI memory.

LifeArchive 是一个独立实现、单用户优先、自托管、面向几十年持续保存的个人记忆系统。日常记录体验借鉴 Memos，但**不依赖 Memos 服务**；AI 采用内置固定工作流，**不依赖 Hermes**。

## 当前状态

- 已实现 M0 基础设施：品牌首页、健康接口、数据库连接模块、迁移基线和容器配置；**不是已完成的日记产品**。
- 尚未实现登录、日记 CRUD、媒体、新闻、AI 或备份。M0 验收通过后再执行 `tasks/01-journal.md`。
- 实际执行结果见 [M0 验收记录](docs/m0-acceptance.md)，扩展入口与下一步见 [开发交接](docs/m0-handoff.md)。
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

## 从零启动 M0

要求 Docker Engine / Docker Desktop 与现代 Docker Compose 插件（支持 `up --wait`）；以下命令在仓库根目录执行。环境初始化脚本需要 Python 3，不会覆盖已有 `.env`，生成的密码不会打印或进入 Git。

```bash
python3 scripts/init-env.py
docker compose config --quiet
docker compose up -d --build --wait
docker compose exec -T api alembic upgrade head
curl --fail http://127.0.0.1:8080/api/v1/health
```

打开 [本地首页](http://127.0.0.1:8080)，健康状态应显示 API 可用；接口返回 `{"status":"ok"}`。该接口只检查 API 存活，不表示数据库、迁移或未来业务依赖就绪。数据库就绪由 Compose 的 PostgreSQL healthcheck 检查；迁移是显式操作，不在 API 启动时运行。

`.env.example` 仅含占位值，不能直接作为有效密码使用。初始化脚本以 `0600` 权限新建 `.env`；已有文件时退出且不修改。手工配置时使用至少 16 字符随机数据库密码。修改 `WEB_PORT` 可换 Web 端口。Compose 内数据库固定使用 `postgres:5432`，不发布数据库、API 或 worker 端口；本机 API 开发时可以覆盖 `POSTGRES_HOST` / `POSTGRES_PORT`。

M0 默认仅绑定 `127.0.0.1`，Caddy 提供 HTTP 开发入口。尚无认证与公网 HTTPS 部署配置，不能当作可存放私人数据的生产发布。`web` 将 `/api`、`/api/*` 原样转发到 API，其他路径支持 SPA 回退。

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

Worker 与 API 共享后端镜像，最后一条命令仅记录“尚未配置任务”后成功退出。M0 默认不启动 worker，也没有调度器或空转循环。Alembic 基线没有业务表，只留下 `alembic_version`；升级可重复执行。

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

打开 [前端开发页](http://127.0.0.1:5173)。Vite 将 `/api` 代理到 `127.0.0.1:8000`；`API_PROXY_TARGET` 可调整开发代理地址。健康页不访问数据库，因此这两个开发进程可以独立检查前后端连接。数据库迁移仍使用 Compose 命令；本机直接运行 Alembic 时需提供可达的 PostgreSQL 配置。

```bash
# 仓库根目录
python3 -m unittest discover -s tests -v

# apps/server
uv run --locked pytest
uv run --locked ruff check . ../../scripts/init-env.py ../../tests
uv run --locked ruff format --check . ../../scripts/init-env.py ../../tests

# apps/web
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
```

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

脚本检查首页和静态资源、API 代理与错误路由、重复迁移、`pgdata` 卷挂载、数据库重启前后迁移版本一致以及 worker 正常退出。CI 自动运行单元检查和相同的 Compose 验收。详见 [验收记录](docs/m0-acceptance.md)。

## 代码目录

```text
apps/web/         React 首页、健康状态、Vite、前端测试与锁文件
apps/server/      FastAPI、配置、SQLAlchemy 会话、Alembic、worker 入口与测试
infra/Caddyfile   静态 SPA 与 /api 代理
compose.yaml      web / api / postgres；worker 为可选 profile
scripts/          安全环境初始化、隔离 Compose 验收
tests/            环境初始化的标准库测试
.github/workflows/ci.yml
docs/             产品/架构设计、M0 验收与后续交接
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
- `docs/decisions.md` — 核心技术决策
- `docs/m0-handoff.md` — M0 实现边界、代码入口和 M1 交接
- `docs/m0-acceptance.md` — 可复核的检查结果与运行限制

## 免责声明

文档包含未来目标与草案，不能当作已实现功能。许可证信息与第三方依赖版本须在实际引入时核验，所有密钥必须通过运行环境配置，禁止进入 Git。
