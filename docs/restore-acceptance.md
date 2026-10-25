# 隔离恢复演练验收

日期：2026-10-25（Asia/Shanghai）；范围 [06 工单](../tasks/06-restore-rehearsal.md)，基线 `07e25bdb2d6771b10c1e3095c97494508ea069e9`，分支 `codex/restore-rehearsal`。精确命令及交接见 [恢复演练](restore-rehearsal.md)。

## 本机检查

- 根目录 unittest：**20 passed**（4 个环境保护、16 个恢复/比较回归）；同样通过 `pytest ../../tests`，包含 30 个 subtests，不重复计数。
- Ruff check / format --check：从 `apps/server` 检查 `. ../../scripts ../../tests` 通过。
- 使用实际 Compose 二进制渲染两个专用 env/override，验证独立项目/卷、run 标签、内部网络、固定镜像、构建上下文和 loopback 端口通过；本机 Docker Engine 不可用，不能将配置检查称为真实恢复。
- 实际无 Docker 执行返回 1，报告失败、未启动目标；私密检查工件保留在 `/Users/gede/.cache/lifearchive-restore-validation-eusyi_u6`，未修改现有数据库或预览配置。
- 首次现有应用 PostgreSQL 测试因原临时 PG 已停止产生连接错误；按原 loopback/UTC 配置启动后重跑，**200 passed，0 skipped**。没有以 skip 充当通过。

拒绝路径覆盖已有工件/符号链接、端口冲突、继承的 Compose/数据库配置、同名或同项目标签资源、非法/重叠 source/target、外部卷/公开 PG 端口/错误资源、目标非空、缺 Docker/超时/失败子进程、恢复失败不重试破坏性参数、不停止归属不符的容器，以及导出元数据/字节/哈希不一致。

## 真实 Docker CI

提交后执行原有 backend/frontend/compose 和新增 restore job。restore job 必须真实完成全新源→dump→全新空目标→restore→字段/导出/HTTP 比较→目标 PG 重启，并另跑损坏备份拒绝流程。当前不宣称该部分已通过；链接、PG/镜像/迁移、项目/卷、数量、dump SHA-256 和比较结果在实测后补记。

## 影响与限制

没有新增应用配置、依赖、迁移、数据库表、worker 或远端备份服务；迁移 head 仍为 `0003_journal`。没有触碰正式数据、已有 `.env` 或 owner，没有删库/删卷、执行恢复清理参数或自动合并。用户 `.DS_Store` 修改保留。

本片只证明当前合成数据路径可恢复，未验收真实历史规模、附件、加密异地副本、备份保留策略或生产 RPO/RTO。脚本只停止已确认归属的自有容器，保留现场；任何后续清理需先列出具体对象并确认。CI 只输出脱敏报告，不上传 dump、导出或秘密。
