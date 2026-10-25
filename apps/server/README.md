# LifeArchive API 与只读日记导出

当前实现 health、单一 owner CLI、Argon2id 登录、可撤销会话/CSRF/限流，以及有版本和创建幂等保护的日记 CRUD。M2 提供月历、日期详情、私密归档搜索和往年今日。`GET /api/v1/on-this-day` 按参考日期读取以前年份同月同日的当前活动原文；省略日期时按 owner 时区确定今天，闰日不映射到相邻日期。搜索通过 `POST /api/v1/search` 的 JSON 请求体接收关键词和日期范围，使用转义的绑定参数做字面子串匹配，不写原文/修订或搜索历史。管理 CLI 另提供原文/元数据/完整所选修订的 ZIP 导出，使用独立只读快照、0600 排他目标和写后哈希复核。没有新闻、AI、媒体或任务调度器。完整运行和验证见根 README、`docs/journal-export-handoff.md`、`docs/export-format.md`。

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

完整集成测试还需显式配置 `TEST_POSTGRES_HOST/PORT/USER/PASSWORD/DB`，指向专门的测试数据库。每项测试迁移新的随机 schema；不提供配置会跳过 PG 测试。CI 会配置真实 PostgreSQL，不能把本机跳过当成全量通过。

Python 固定为 `.python-version` 的 3.12.14，uv 固定为 `pyproject.toml` 的 0.12.17。依赖使用清华 PyPI 镜像，版本和下载哈希记录在 `uv.lock`。如镜像速度较慢，可在安装时设置 `UV_HTTP_TIMEOUT=120`；切换镜像需要重新生成并审查锁文件。

`GET /api/v1/health` 始终只返回 `{"status":"ok"}`，不访问数据库，不代表数据库或业务可用。开发模式绑定 loopback；生产入口由 Caddy 提供。OpenAPI/Swagger/ReDoc 保持关闭。

## 模块与约定

| 文件 | 责任 |
| --- | --- |
| `src/life_archive/main.py` | 组装 health/auth/journal/timeline/search、验证错误脱敏和私密响应 no-store |
| `src/life_archive/auth/` | owner、Argon2id、会话摘要、CSRF、共享限流、认证依赖 |
| `src/life_archive/journal/` | owner 范围读写、原子修订、标签目录/关联/历史、分页与创建请求去重 |
| `src/life_archive/timeline/` | owner 范围月历、日期详情和往年今日；后者在 on_this_day.py 使用独立绑定游标 |
| `src/life_archive/search/` | owner 范围只读搜索、JSON 校验和条件摘要绑定的独立游标 |
| `src/life_archive/cli.py` | 唯一 owner 初始化（密码 getpass / stdin）与 export-journal 脱敏分发 |
| `src/life_archive/journal/export.py` | 只读快照、批量原文/修订、私密排他 ZIP 和完整校验 |
| `src/life_archive/settings.py` | Pydantic 配置；普通应用配置和 DB 密钥分别延迟读取 |
| `src/life_archive/db.py` | DeclarativeBase、延迟创建的 engine、每次请求独立的同步 Session |
| `src/life_archive/worker.py` | 独立进程入口；M0 记录一条日志并正常退出 |
| `alembic/env.py` | 仅迁移命令创建 DB 连接；从运行环境读取密钥 |
| `alembic/versions/0001_foundation.py` | 无业务表的基线；Alembic 自行维护版本表 |

本地命令固定从 `apps/server` 执行，配置读取相对当前目录的 `../../.env`。进程环境变量优先于文件；容器通过 Compose 注入环境变量，不复制 `.env`。

应用配置使用 `LIFEARCHIVE_` 前缀；`LIFEARCHIVE_LOG_LEVEL` 控制 worker 日志。数据库使用 `POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`。密码至少 16 字符且不能是示例占位符，实际部署应使用随机生成的强密码。只有调用 DB/在线迁移时才要求数据库密码。配置和 engine 按进程缓存；修改配置后重启进程。

数据库密码通过 `SecretStr` 保存，用 SQLAlchemy `URL.create()` 组合 URL，支持 `@`、`%`、`/` 等特殊字符。不要打印 URL 的明文密码或配置对象的底层值。SQL 参数不写入数据库异常日志；连接会话时区固定为 UTC。

业务服务显式管理提交和回滚；`get_db_session()` 只负责关闭连接和回滚未提交事务，绝不自动提交。认证查询可能已经开启事务，不要在 journal 服务再嵌套 `session.begin()`。同步数据库访问应放在普通 `def` 路由/依赖中，避免阻塞异步事件循环。表结构只经 Alembic 修改，不在 API 启动时执行 `create_all()` 或自动迁移。

## 导出 CLI

从仓库根目录，已有实例运行 `docker compose exec -T api python -m life_archive.cli export-journal --output /tmp/new-journal.zip`。本机从 apps/server 使用 `uv run --locked python -m life_archive.cli export-journal --output /absolute/new-journal.zip`，复用数据库环境配置。默认仅活动日记和全部修订；新路径配合 `--include-deleted` 包含软删除记录。绝对新路径、已存在父目录、0600、只读一致性和禁止覆盖为固定约定；无 HTTP 导出接口或任务队列。详见格式文档和交接；不将可阅读导出称为整个部署的可恢复备份。

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

新增 ORM 模型时继承 `Base`，在 `alembic/env.py` 中导入模型，再生成并审查新迁移。当前 head 为 `0004_entry_tags`，新增标签与关联，旧修订标签回填 `[]`。不要修改已应用的迁移；不要一次创建设计文档中的全部未来表。单元测试中的 SQLite 仅验证基础 Session 行为，业务、并发和迁移用真实 PostgreSQL。

当前范围还包括 `tasks/08-journal-tags.md`：私密标签、随日记保存、历史和列表筛选、导出 v2。标签位于 journal 模块，没有独立服务；归档搜索暂不支持标签条件。后续仅执行明确分配的工单。当前搜索未增加全文索引，不承诺大规模数据性能。继续保持 API 与 worker 入口独立；worker 使用 `python -m life_archive.worker`，没有调度器、业务任务或常驻循环。

实现依据：[SQLAlchemy URL](https://docs.sqlalchemy.org/en/20/core/engines.html#creating-urls-programmatically)、[Session 生命周期](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)、[Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)、[Alembic 教程](https://alembic.sqlalchemy.org/en/latest/tutorial.html)、[uv 容器部署](https://docs.astral.sh/uv/guides/integration/docker/)。
