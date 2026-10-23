# M0 验收记录

验证日期：2026-10-24（Asia/Shanghai）。范围为 `tasks/00-foundation.md`；没有实现 M1 日记、登录或后续新闻/AI 功能。

## 本机已执行

环境：macOS arm64、Python 3.12.14、uv 0.12.17、Node 24.19.0、npm 11.17.0。依赖优先从清华 PyPI / npmmirror 安装；锁文件提交源码，虚拟环境、node_modules、构建产物和 `.env` 不提交。

| 检查 | 工作目录 / 命令 | 结果 |
| --- | --- | --- |
| 配置初始化保护 | 根目录：`python3 -m unittest discover -s tests -v` | 4 passed：随机密码、0600 权限、拒绝覆盖/符号链接、错误模板不产生文件 |
| 后端测试 | `apps/server`：`uv run --locked pytest` | 19 passed |
| 环境隔离 | `apps/server`：`LIFEARCHIVE_LOG_LEVEL=invalid POSTGRES_PASSWORD=invalid uv run --locked pytest` | 19 passed；是同一套测试的额外验证，不计为另外 19 项 |
| Python lint | `apps/server`：`uv run --locked ruff check . ../../scripts/init-env.py ../../tests` | 通过 |
| Python 格式 | `apps/server`：`uv run --locked ruff format --check . ../../scripts/init-env.py ../../tests` | 16 文件通过 |
| 后端锁一致性 | `apps/server`：`uv lock --check --offline` | 36 个解析包，通过 |
| 离线 PostgreSQL 迁移 SQL | `apps/server`：`uv run --locked alembic upgrade head --sql` | 通过，仅建立 `alembic_version` 并写入 `0001_foundation`；不等于在线数据库验证 |
| Worker 独立入口 | `apps/server`：`uv run --locked python -m life_archive.worker` | 单条说明日志后正常退出 0，无调度器 |
| 前端 lint / 格式 / 类型 | `apps/web`：`npm run lint`、`npm run format:check`、`npm run typecheck` | 全部通过 |
| 前端行为测试 | `apps/web`：`npm run test` | 10 passed；成功/失败/响应结构/重试/超时等 |
| 前端构建 | `apps/web`：`npm run build` | 通过，生成 HTML、JS、CSS |
| 前端依赖 | `apps/web`：`npm ls --depth=0` | 无 peer 错误 |
| 验收脚本语法 | 根目录：`bash -n scripts/smoke-compose.sh`，内嵌 Python AST 解析 | 通过 |
| CI 语义 | 根目录：`GOPROXY=https://goproxy.cn,direct go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.12 -shellcheck='' .github/workflows/ci.yml` | 通过；本机没有 ShellCheck，未宣称执行 ShellCheck |
| Compose 配置 | 官方 Compose v5.6.1 独立二进制：`compose --profile worker config --quiet` | 通过；本机未安装 Docker CLI/Engine，使用 standalone CLI 做配置校验 |
| Caddy 配置 | 官方 Caddy v2.11.7：`caddy validate --config infra/Caddyfile --adapter caddyfile`、`caddy fmt --diff infra/Caddyfile` | 有效、格式一致 |
| 补丁空白检查 | 根目录：`git diff --check` | 通过 |

不重复计数：后端 19 + 前端 10 + 配置脚本 4 = **33 项测试通过**。

Compose/Caddy 使用官方 release 二进制并核对 GitHub asset SHA-256；只在仓库外用于验证，未将其作为源码提交。Docker Registry API 确认 Node、Python、PostgreSQL、Caddy 所用精确标签存在且包含 linux/amd64 与 linux/arm64；这不能替代实际镜像构建。

## 实际前后端联调

使用构建出的 `apps/web/dist`、原生 Caddy 2.11.7 和 Uvicorn 完成真实 HTTP 联调。临时 Caddy 配置只把监听地址绑定到 `127.0.0.1:18880`、上游换为 `127.0.0.1:18881`、静态目录换成本机构建目录，并禁用配置持久化；仓库内路由规则保持一致。

- `scripts/smoke-compose.sh` 的 Web 检查部分通过：健康 JSON、首页、编译后 JS/CSS、SPA 回退、未知 API 返回 JSON 404。
- Chrome headless 真正执行 React 与健康请求，桌面 1440×1000 和移动 390×844 均显示“服务已连接”；3 个未来导航项均禁用。
- 两个尺寸的页面 scrollWidth 分别等于 1440 / 390，无水平溢出；已检查实际截图。

这验证了浏览器 → Caddy → API 的链路，但**没有验证 Docker 网络、镜像构建或真实 PostgreSQL**。

## 容器与 PostgreSQL 验收状态

本机没有 Docker CLI / Docker Engine / Docker Desktop，因此以下项目在本机**未执行**：

1. `docker compose up -d --build --wait` 实际构建与启动全部服务。
2. 容器网络中执行 `alembic upgrade head` 两次并读取 `alembic current`。
3. PostgreSQL `pgdata` 命名卷的重启持久化验收。
4. 同一后端镜像启动 worker 并正常退出。

这些步骤已接入 `.github/workflows/ci.yml`；结果以 PR 的实际 Actions 运行记录为准。完成前不要把 M0 标为全部验收通过，也不要直接启动 M1。

本机或 CI 的精确复核命令见 README 的“隔离的完整验收”。持久化脚本会：确认 PostgreSQL 挂载本项目 `pgdata` 命名卷 → 执行两次迁移 → 读取 `alembic_version` → 重启 PostgreSQL → 等待就绪 → 确认版本行不变并由 API 再次读取迁移状态。基线版本记录是测试数据，不创建额外业务表；此方法覆盖任务要求的重启保存，不声称完成备份恢复验证。

## 交付边界

- 迁移影响：仅 Alembic 版本基线；无用户/日记/任务业务表。API 启动不自动迁移。
- M0 为 loopback HTTP 开发栈，无 owner 认证、生产 HTTPS、媒体、备份或导出功能。
- `.env`、依赖目录、二进制与构建产物均忽略；原有已跟踪 `.DS_Store` 的用户改动保持不动、不纳入本次提交。
- 下一步严格为 `tasks/01-journal.md`，按 [开发交接](m0-handoff.md) 的切片推进，先补齐/确认 M0 容器验收。
