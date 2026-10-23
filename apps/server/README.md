# LifeArchive 后端基础设施（M0）

当前只有进程健康检查、配置、数据库会话与迁移骨架。没有认证、日记、新闻、AI 或任务调度器。完整启动和验收方法见仓库根目录 `README.md`。

## 开发与检查

在仓库根目录执行：

```sh
cd apps/server
uv sync --locked --dev
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked uvicorn life_archive.main:app --reload --host 127.0.0.1 --port 8000
```

Python 固定为 `.python-version` 的 3.12.14，uv 固定为 `pyproject.toml` 的 0.12.17。依赖使用清华 PyPI 镜像，版本和下载哈希记录在 `uv.lock`。如镜像速度较慢，可在安装时设置 `UV_HTTP_TIMEOUT=120`；切换镜像需要重新生成并审查锁文件。

`GET /api/v1/health` 始终只返回 `{"status":"ok"}`，不访问数据库，不代表数据库或未来业务可用。开发模式绑定 loopback；生产入口由 Caddy 提供。M0 关闭 OpenAPI/Swagger/ReDoc。

## 模块与约定

| 文件 | 责任 |
| --- | --- |
| `src/life_archive/main.py` | FastAPI 工厂与固定 `/api/v1/health` 路由 |
| `src/life_archive/settings.py` | Pydantic 配置；普通应用配置和 DB 密钥分别延迟读取 |
| `src/life_archive/db.py` | DeclarativeBase、延迟创建的 engine、每次请求独立的同步 Session |
| `src/life_archive/worker.py` | 独立进程入口；M0 记录一条日志并正常退出 |
| `alembic/env.py` | 仅迁移命令创建 DB 连接；从运行环境读取密钥 |
| `alembic/versions/0001_foundation.py` | 无业务表的基线；Alembic 自行维护版本表 |

本地命令固定从 `apps/server` 执行，配置读取相对当前目录的 `../../.env`。进程环境变量优先于文件；容器通过 Compose 注入环境变量，不复制 `.env`。

应用配置使用 `LIFEARCHIVE_` 前缀；`LIFEARCHIVE_LOG_LEVEL` 控制 worker 日志。数据库使用 `POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`。密码至少 16 字符且不能是示例占位符，实际部署应使用随机生成的强密码。只有调用 DB/在线迁移时才要求数据库密码。配置和 engine 按进程缓存；修改配置后重启进程。

数据库密码通过 `SecretStr` 保存，用 SQLAlchemy `URL.create()` 组合 URL，支持 `@`、`%`、`/` 等特殊字符。不要打印 URL 的明文密码或配置对象的底层值。SQL 参数不写入数据库异常日志；连接会话时区固定为 UTC。

业务服务显式管理事务，例如 `with session.begin(): ...`；`get_db_session()` 只负责关闭连接和回滚未提交事务，绝不自动提交。同步数据库访问应放在普通 `def` 路由/依赖中，避免阻塞异步事件循环。表结构只经 Alembic 修改，不在 API 启动时执行 `create_all()` 或自动迁移。

## 迁移与下一阶段

无需数据库即可审查基线 SQL：

```sh
uv run --locked alembic upgrade head --sql
```

在线迁移优先从已启动的 Compose 网络运行（仓库根目录）：

```sh
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic current
```

M1 新增 ORM 模型时，继承 `Base`，在 `alembic/env.py` 中导入模型，再生成并审查新迁移。不要修改已应用的基线迁移；不得一次创建 `docs/data-model.md` 中的全部未来表。真实 PostgreSQL 的连接、重复迁移和重启持久化需要运行集成验收；单元测试中的 SQLite 仅验证 Session 的提交/回滚行为。

后续范围严格以 `tasks/01-journal.md` 为准。继续保持 API 与 worker 入口独立；M0 worker 使用 `python -m life_archive.worker`，没有调度器、业务任务或常驻循环。

实现依据：[SQLAlchemy URL](https://docs.sqlalchemy.org/en/20/core/engines.html#creating-urls-programmatically)、[Session 生命周期](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)、[Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)、[Alembic 教程](https://alembic.sqlalchemy.org/en/latest/tutorial.html)、[uv 容器部署](https://docs.astral.sh/uv/guides/integration/docker/)。
