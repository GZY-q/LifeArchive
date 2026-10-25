# 只读日记导出验收

日期：2026-10-25（Asia/Shanghai）。范围 [05 工单](../tasks/05-journal-export.md)，基线 `97b53106265a4ddf02885c3437a6def773ef44a5`，分支 `codex/journal-export`。格式与精确命令见 [格式文档](export-format.md) 和 [交接](journal-export-handoff.md)。

## 本机验证

| 检查 | 结果 |
| --- | --- |
| 后端 `pytest -q --tb=short` | **200 passed，0 skipped**，独立 PostgreSQL 17.11 |
| 导出与 owner CLI 专项 | **21 passed**，包含在上述 200 项中 |
| 前端 lint / format:check / typecheck / test / build | 全部通过，**97 tests / 11 files** |
| 根目录环境保护 unittest | **4 passed** |
| Ruff check / format --check | 从 `apps/server` 执行 `. ../../scripts ../../tests`，通过 |
| Compose 含 worker 配置 | `--profile worker config --quiet` 通过；本机无 Docker Engine，容器验收由 CI 执行 |

共 **301 项自动测试**。新增 16 项覆盖原始中文/emoji/CRLF/尾空格/Unicode、年份 1/9999、UTC/时区/null、当前和历史元数据、全部修订、软删除策略、空档案、103 篇/203 修订跨批次、重复导出数据文件稳定、源日记/修订/认证表不变、既有文件/目录/符号链接/悬空链接拒绝、不可写目录、缺 owner/迁移、配置错误脱敏、中断退出码 130、损坏内容不能返回成功。

并发测试在第一个成员写入时，用第二个数据库连接编辑一篇并软删另一篇；导出仍包含修改前的两个原文及 revision 1，没有混入新修订或改变成员集合。同时检查 PostgreSQL `transaction_isolation=repeatable read` 和 `transaction_read_only=on`。

## 实际 CLI 合成样本

新建专用数据库 `life_archive_export_smoke_518e25510b`，显式迁移、初始化合成 owner，写入/修订/软删两篇合成日记，然后在子进程运行实际 `python -m life_archive.cli export-journal`。结果：

| 包 | 当前日记 | 修订 | 已验证数据文件 | ZIP SHA-256 |
| --- | ---: | ---: | ---: | --- |
| active.zip | 1 | 2 | 6 | `5d0f67af86105ced3adb0d3c81d5f24a9d9433233d099cc05963c144460faa54` |
| with-deleted.zip | 2 | 4 | 12 | `26fd37af9236cfc58b42957b056b386f1814cd0aeaed3137beb65d6639c106d9` |

独立打开 ZIP，逐项核对清单、字节长度、SHA-256、CRLF 保留和 0600；重复执行到同路径返回 1，原文件字节未变。对 User/Session/Throttle/Entry/Revision 导出前后计算相同源指纹，确认源数据未写入。

从格式文档直接提取独立 Python 核验命令，对两个包分别得到 `1 entries, 2 revisions, 6 files verified` 和 `2 entries, 4 revisions, 12 files verified`。`scripts/smoke-export.py` 也在该原生隔离实例中通过；这验证脚本本身，容器镜像仍以 CI 结果为准。

工件与 `report.json` 位于仓库外 `/Users/gede/.cache/lifearchive-export-validation-husyd6pz`（目录 0700、文件 0600），保留供本机检查，未提交 ZIP、数据库或秘密；没有删除新数据库或工件。报告记录实际 CLI/export 源文件的 SHA-256，可与提交内容复核。已有预览库未用于本次导出样本。

## CI

[PR #6](https://github.com/GZY-q/LifeArchive/pull/6) 的实现提交 `8e4c0d182346c3bf64d2f7075a977d9cd22a6d0e` 在 [CI run 40189688949](https://github.com/GZY-q/LifeArchive/actions/runs/40189688949) 完整通过：

- backend：200 项真实 PostgreSQL 测试、4 项环境保护测试及 Ruff 检查通过。
- frontend：97 项测试、lint、格式、类型、生产构建通过。
- compose：Docker 镜像构建、Caddy、重复迁移、PG 重启持久化、独立 worker、HTTP 与 Linux Chrome 全部通过。新增镜像内 CLI 验收明确输出 `PASS: installed CLI exports, SHA-256, 0600, deleted policy, overwrite refusal, source unchanged`。

Git 推送凭据缺少 workflow scope，工作流变更通过已连接且有权限的 GitHub 应用发布分支；没有删减验收或更改依赖源。后续证据提交只更新文档和 PR 链接；审阅时同时核对最新 head 的检查状态。

## 影响与限制

无新应用配置、依赖、数据表或迁移，head 为 `0003_journal`。没有覆盖已有 `.env`、重置 owner、迁移回滚、删库/删卷或自动合并。保留用户 `.DS_Store` 修改。

导出不含媒体/标签、认证哈希/会话、环境/日志或 AI；文件未加密，当前没有导入/整库恢复功能。大档案性能和正式备份恢复仍需后续验收，见 [06 工单](../tasks/06-restore-rehearsal.md)。
