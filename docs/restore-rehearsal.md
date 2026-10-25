# 独立 PostgreSQL 恢复演练

本片 [PR #7](https://github.com/GZY-q/LifeArchive/pull/7) 实现 [06 工单](../tasks/06-restore-rehearsal.md)，验收证据见 [恢复验收](restore-acceptance.md)。脚本只建立自己的合成源、目标项目，不接受正式数据库 URL、已有项目名或外部 dump。其结果用于验证当前日记数据路径可恢复，不代表生产备份、媒体恢复或 RPO/RTO 已验收。

## 精确运行

要求本机可用 Docker Engine 和支持 `up --wait` 的现代 Docker Compose，以及 Python 3.9+；源代码根目录执行，无需宿主安装 PostgreSQL/Python 应用依赖。镜像按现有锁文件构建，pg_dump/pg_restore 直接使用固定 PG 镜像内工具。

先选择已存在父目录下、从未创建过的绝对工件路径，以及两个空闲的非特权端口：

```bash
python3 scripts/smoke-restore.py \
  --artifact-dir /absolute/private-parent/new-restore-report \
  --source-port 18082 --target-port 18083
```

工件目录以 0700 排他创建，内部文件为 0600。已有文件/目录/符号链接、端口相同/被占用、Docker 不可用或任何验证失败都会非零退出。失败后保留现场，再次运行请选新路径。初始参数/创建失败时可能还没有报告；进入演练后写 `report.json`，只打印脱敏报告和阶段结果。

| 退出码 | 语义 |
| --- | --- |
| 0 | 正常演练及停止自有容器全部通过 |
| 1 | 拒绝、Docker/构建/备份/恢复/比较/停止等失败 |
| 2 | 参数非法或缺失，由 argparse 拒绝 |
| 130 | 中断；仍尝试只停止已确认归属的项目并保留现场 |

## 隔离和执行顺序

1. 生成 32 位随机 run ID，源和目标项目固定为 `life-archive-restore-<run>-source/target`，使用独立密码、env 文件和 pgdata 卷。清除继承的 POSTGRES/LIFEARCHIVE/COMPOSE 配置、WEB_PORT/NPM_REGISTRY，显式指定 Compose 文件、项目目录、专用 env 文件和项目名，并关闭默认 env 文件加载。
2. 创建资源前检查同名/同前缀/同项目标签的容器、网络、卷均不存在。审查实际渲染配置的 run 标签、构建上下文、独立卷、固定 PG 镜像、内部数据库网络和 loopback Web 端口；数据库/API/worker 无公开端口。
3. 源项目从当前代码构建自有镜像标签，显式升级 Alembic head，生成临时 owner、3 篇合成日记/6 个修订，其中 1 篇软删除。样本包含中文、emoji、CRLF、尾空格、同日多篇、闰日补记、跨 UTC 日界及真实修订。
4. 保存源的 owner/迁移/日记/修订摘要并经 HTTP 读取；运行 `--include-deleted` 应用导出。通过源 PG 容器执行 `pg_dump --format=custom --no-owner --no-acl`，直接写入排他 0600 文件并记录 SHA-256。
5. 仅启动新目标 PostgreSQL，核验两容器/卷不同、实际 run/项目标签、PG 无公开端口且挂载独立卷/内部网络。目标 API/web 尚不存在，库内无应用关系后才执行 `pg_restore --exit-on-error --single-transaction --no-owner --no-acl`，不预跑迁移。
6. 成功后才启动目标应用，比较原文和修订全部实际字段、owner 公共元数据、迁移 head，正常登录验证恢复的密码哈希可用。比较源/目标导出的每个数据文件路径、字节、长度与 SHA-256，只允许清单生成时刻不同。
7. 经 HTTP 验证活动列表、原文/历史、软删除不可见、月历/日期、搜索和往年今日；重启目标 PG 后重读并再次比较。核对源日记/修订摘要未改变，源/目标 API 与 PG 镜像身份一致。
8. 最后只对本次已核实 run/项目标签的容器执行 `docker compose stop`。保留停止的容器、网络、数据卷、镜像和私密工件；不自动删除或覆盖。无法确认归属时拒绝停止并标记失败。

登录会改变 sessions/throttle，日记/修订摘要不把这些认证运行状态当成原文变化。报告不包含密码、认证哈希、正文、dump 或导出文件内容。

## 损坏备份测试

在另一个全新工件路径和独立端口执行：

```bash
python3 scripts/smoke-restore.py \
  --artifact-dir /absolute/private-parent/new-negative-report \
  --source-port 18084 --target-port 18085 --corrupt-test-dump
```

此开关只生成新的合成损坏文件，不修改有效 dump，也不接受外部 dump。预期返回 **1**，报告 `status=failed`、`target_app_started=false`、阶段为 `restore database`，并记录 `corrupt_dump_refused/target_still_empty/source_unchanged/owned_projects_stopped=true`。不能把这次预期失败当作恢复成功；CI 单独核对这些条件。

## 工件和检查

目录包含专用 source/target.env、compose.images.json、owner-password.txt、database.dump、源/目标导出（成功时）和 report.json；损坏测试还含 corrupt-test.dump。完整数据库 dump 包含认证哈希，工件保持私密，不上传到 Git/CI 工件。CI 仅打印脱敏 JSON，临时 runner 销毁后这些文件不长期保留。

本机可通过报告的 run ID 查看停止的自有容器：

```bash
docker container ls --all --filter label=life_archive.restore_run=<report中的run_id>
docker volume ls --filter label=life_archive.restore_run=<report中的run_id>
```

清理是独立操作：先列出确切项目、容器、卷、镜像和路径及影响，等待用户确认。不要通过删除卷重试或覆盖现有目标来解决失败。

## 接手入口与验证命令

- `scripts/smoke-restore.py`：参数、完整正向/损坏测试编排和报告。
- `scripts/restore_support.py`：Compose 环境隔离、资源归属、空目标和停止边界。
- `scripts/restore_fixture.py`：仅在新源 API 镜像内生成合成夹具；源/目标只读快照。
- `scripts/restore_checks.py`：HTTP 与导出字节/哈希比较。
- `tests/test_restore_rehearsal.py`：无 Docker 的拒绝/失败路径回归；它不能代替真实演练。

根目录运行 `python3 -m unittest discover -s tests -v`。从 `apps/server` 运行：

```bash
uv run --locked pytest ../../tests
uv run --locked ruff check . ../../scripts ../../tests
uv run --locked ruff format --check . ../../scripts ../../tests
```

CI 的独立 `restore` job 在真实 Docker 环境执行正常和损坏两条流程；现有 backend/frontend/compose 检查继续运行。没有应用表、迁移、依赖或新服务变更，当前 head 为 `0003_journal`，运行时从镜像迁移链确认，不伪造更高版本。

本轮基于导出 PR #6 的 `07e25bdb2d6771b10c1e3095c97494508ea069e9`，分支 `codex/restore-rehearsal`。前序 PR 仍待合入，继续按依赖审阅；下一张 [07 真机输入法](../tasks/07-editor-compatibility.md) 尚未实施。
