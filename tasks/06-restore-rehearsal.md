# Task 数据可恢复门槛 — 隔离 PostgreSQL 恢复演练

状态：用户要求继续后，本轮实施；一个 PR。前序 PR #2–#6 尚未合入，本轮沿用堆叠交付，在 `codex/restore-rehearsal` 接续草稿，基线为导出 PR #6 的 `07e25bdb2d6771b10c1e3095c97494508ea069e9`，PR base 为 `codex/journal-export`。本片只使用脚本自己创建的合成日记实例，证明当前数据库能恢复到独立新环境；不是生产备份部署或正式数据恢复授权。

## 固定流程与安全边界

新增 `scripts/smoke-restore.py`，计划入口：

```bash
python3 scripts/smoke-restore.py --artifact-dir /absolute/new-restore-report --source-port 18082 --target-port 18083
```

1. `--artifact-dir` 必须为未存在绝对路径，排他创建且权限 0700。脚本生成唯一 `life-archive-restore-<随机标识>-source` 和 `...-target` Compose 项目名；不接受任意 source/target 数据库 URL、项目名或已有 dump 输入。不读取工作区正式 `.env`；为两个实例生成专用环境文件/秘密并限制为 0600，不输出秘密。
2. 启动之前检查两项目对应容器、网络、卷均不存在，并确认 Compose 渲染结果的项目、卷、内部 PG 网络与 loopback 端口符合预期。任一对象已存在或端口被占用立即退出，不复用、停止、重置或删除它。源与目标卷必须不同；禁止 PostgreSQL 公开端口。
3. 从当前仓库构建镜像，初始化新的 source、显式迁移、创建临时 owner。写入合成夹具：中文/Markdown/emoji、UTC 日界和补记、同日多篇、至少两次修订及一篇软删除。只操作脚本自己创建的记录；不借用当前本机预览实例。
4. 使用 source 容器内与数据库版本一致的 `pg_dump --format=custom --no-owner --no-acl` 建立一致性备份。dump 排他写入 0600 文件并计算 SHA-256；禁止把二进制、日记、数据库密码或认证字段打印/上传。整个数据库 dump 含认证哈希，不能当作脱敏应用导出。
5. 启动全新 target 的 PostgreSQL 空数据库，**不要先跑应用迁移**。再次检查目标身份/卷和库内无应用表。使用 `pg_restore --exit-on-error --single-transaction --no-owner --no-acl` 恢复，禁止 `--clean`、删除 schema、覆盖既有表、恢复到 source 或现有部署。失败退出，不启动目标应用，不偷偷改用破坏性选项。
6. 恢复成功后启动 target API/web，并执行下面的完整比较。停止脚本自己的容器时使用 `docker compose stop`，保留项目、数据卷和私密工件供检查；不自动删除。重复演练创建新项目/目录。清理必须另行列出具体项目、卷、路径及影响，等待用户确认。

子进程使用参数数组和明确项目/配置，避免 shell 字符串拼接。Compose 的 `.env` 自动加载行为也必须被显式隔离；不能只替换 `COMPOSE_PROJECT_NAME` 就声称隔离成功。不得把 dump、导出、环境文件、浏览器截图或秘密放进版本库或 CI 公共工件。

## 必须比较的结果

- 源和目标 Alembic revision 等于当前 head；当前基线是 `0003_journal`，执行时从仓库迁移链确认，不提前伪造更高版本。目标不是靠迁移重建空表后只检查 health。
- owner ID/用户名/时区/创建时间相同，目标通过正常登录验证恢复后的密码哈希可用；不打印或把哈希写进报告。未登录私密请求仍 401。
- 当前日记和修订的 ID、归属、内容 UTF-8 字节、修订号、`entry_date`、所有已有 UTC instant、occurred timezone/null、`deleted_at` 和创建幂等键逐项相同；软删除默认不可见、历史仍保留。
- source 和 target 分别运行 05 的 `--include-deleted` 导出，比较对应数据文件路径/字节/SHA-256。清单的生成时刻可不同，不能因此忽略数据文件差异；同时核对 owner 元数据、软删除策略和数量。
- 对恢复库执行活动日记读取、历史、月历/日期、搜索、往年今日样本检查；目标 PG 重启后再读核心日记/修订，证明并非仅容器内临时结果。
- 演练前后 source 的日记/修订校验值不变。登录会影响 sessions/throttle；这些认证运行状态不参与“原文完全未写入”的比较，但禁止修改源日记来迁就目标差异。

## 实现入口与交付

复用 `compose.yaml` 及 `scripts/smoke-journal.py` 的测试实例约束、HTTP 客户端和夹具思路；需要可复用帮助函数时仅做小范围提取，不能改成通用部署框架。脚本参数/项目隔离/排他工件/目标存在拒绝行为放在 `tests/` 的脚本测试中；新增 `docs/restore-rehearsal.md`，记录精确运行步骤、合成数据量、比较结果、保留对象和限制。

无应用表、迁移、队列、worker、远端备份服务或新 Python 依赖。使用当前固定 PostgreSQL 镜像的 pg_dump/pg_restore，不依赖宿主随意安装的不同主版本工具。

## 验收

- 在干净隔离实例真实执行一次完整流程；记录日期、代码 revision、镜像/PG 版本、源/目标项目和迁移、日记/修订数量、dump SHA-256 与各项比较 pass/fail。报告只包含合成数据和必要统计，不附秘密或 dump。
- 单测验证已有目标对象、非法/相同目标、现有工件路径、缺失 Docker、失败子进程会停止对应步骤，且没有执行删除/覆盖命令。损坏 dump 的隔离测试返回失败，不能声称恢复完成。
- 从 `apps/server` 运行 `uv run --locked pytest ../../tests` 和仓库既有 ruff 检查；再运行上面的真实 Docker 演练命令。单测模拟 subprocess 通过不能替代一次真实恢复；没有 Docker 时明确未验收，不能勾选完成。
- README/交接说明该演练证明当前合成数据路径可恢复，尚未覆盖实际历史数据量、附件、远端备份或生产 RPO/RTO。定时/加密异地备份及完整冷恢复仍在 M5。

排除：恢复到既有库、通用应用导入器、正式数据迁移、Restic/远端凭据、自动清理卷、媒体一致性备份、跨 PostgreSQL 大版本升级、生产密码轮换。遇到这些需求另开明确工单。
