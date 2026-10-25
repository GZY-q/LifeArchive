# 隔离恢复演练验收

实施始于 2026-10-25（Asia/Shanghai），CI 实际时刻见下方报告；范围 [06 工单](../tasks/06-restore-rehearsal.md)，基线 `07e25bdb2d6771b10c1e3095c97494508ea069e9`，分支 `codex/restore-rehearsal`。精确命令及交接见 [恢复演练](restore-rehearsal.md)。

## 本机检查

- 根目录 unittest：**20 passed**（4 个环境保护、16 个恢复/比较回归）；同样通过 `pytest ../../tests`，包含 30 个 subtests，不重复计数。
- Ruff check / format --check：从 `apps/server` 检查 `. ../../scripts ../../tests` 通过。
- 使用实际 Compose 二进制渲染两个专用 env/override，验证独立项目/卷、run 标签、内部网络、固定镜像、构建上下文和 loopback 端口通过；本机 Docker Engine 不可用，不能将配置检查称为真实恢复。
- 实际无 Docker 执行返回 1，报告失败、未启动目标；私密检查工件保留在 `/Users/gede/.cache/lifearchive-restore-validation-eusyi_u6`，未修改现有数据库或预览配置。
- 首次现有应用 PostgreSQL 测试因原临时 PG 已停止产生连接错误；按原 loopback/UTC 配置启动后重跑，**200 passed，0 skipped**。没有以 skip 充当通过。

拒绝路径覆盖已有工件/符号链接、端口冲突、继承的 Compose/数据库配置、同名或同项目标签资源、非法/重叠 source/target、外部卷/公开 PG 端口/错误资源、目标非空、缺 Docker/超时/失败子进程、恢复失败不重试破坏性参数、不停止归属不符的容器，以及导出元数据/字节/哈希不一致。

## 真实 Docker CI

[PR #7](https://github.com/GZY-q/LifeArchive/pull/7) 的实现提交 `b303271214ad80eb4b34b9b8cca965bfae6e508f` 在 [CI run 40209529224](https://github.com/GZY-q/LifeArchive/actions/runs/40209529224) 四项 job 全部通过：backend（200 个真实 PG 测试 + 20 个脚本测试）、frontend（97 个测试及 lint/格式/类型/构建）、既有 compose 回归和新增 restore。共 **317 项自动测试**，另有完整真实恢复与损坏备份两条验收。

正常流程报告：

| 项目 | 实测值 |
| --- | --- |
| 报告 UTC 时刻 | `2026-10-25T16:00:37.790017+00:00` |
| 实际构建/运行代码 | CI merge commit `bef7c404afcb3c048ff34a6cab43d037af50c6a9` |
| PG 版本 | `17.11 (Debian 17.11-1.pgdg12+2)` |
| 迁移 | `0003_journal`，源/目标均与镜像迁移链 head 相同 |
| 合成数据 | 3 篇、6 个修订、1 篇软删除；可移植导出 18 个数据文件 |
| PG 镜像身份 | `sha256:e4bdd2f9eeabc0f516e1fa42c4acea97ae571f20877982ac082921b205a52618`，源/目标相同 |
| API 镜像身份 | `sha256:60db8e349a86460f782805d2aba0bb1bdc4e70c521f430c4c273194f8f8aeee9`，源/目标相同 |
| Dump SHA-256 | `afeb084d40603607933c798e1a261c83dec1a90c8338652f42951df44f6c08ee` |

| 角色 | Compose 项目 | PG 数据卷 |
| --- | --- | --- |
| source | `life-archive-restore-bff1c3a226862881ab62359acdafbfa6-source` | `life-archive-restore-bff1c3a226862881ab62359acdafbfa6-source_pgdata` |
| target | `life-archive-restore-bff1c3a226862881ab62359acdafbfa6-target` | `life-archive-restore-bff1c3a226862881ab62359acdafbfa6-target_pgdata` |

正常报告 `status=passed`；空目标恢复、owner/迁移/原文/修订、正常登录与 HTTP 视图、导出全部文件字节/哈希、目标 PG 重启、源数据未变和只停止自有容器均为 true。端口分别为 18082/18083。

损坏流程使用另一个随机 run ID `07ed5fbb22124c9152aa795a300e6a03` 的 source/target 项目、独立卷和 18084/18085 端口。脚本按预期返回 1，`status=failed`、阶段 `restore database`、`target_app_started=false`；`corrupt_dump_refused/target_still_empty/source_unchanged/owned_projects_stopped` 全部为 true。CI 包装检查这些条件后成功退出，没有将预期失败标为恢复成功。

仅脱敏 JSON 报告写入 CI 日志；dump/导出/env/密码未上传。脚本只停止自己的已核实容器；临时 runner 结束后其工件不持久保留。本机仍保留上面的配置/缺 Docker 检查现场。后续证据提交仅更新文档和 PR 链接，审阅时同时核对最新 head 的检查状态。

## 影响与限制

没有新增应用配置、依赖、迁移、数据库表、worker 或远端备份服务；迁移 head 仍为 `0003_journal`。没有触碰正式数据、已有 `.env` 或 owner，没有删库/删卷、执行恢复清理参数或自动合并。用户 `.DS_Store` 修改保留。

本片只证明当前合成数据路径可恢复，未验收真实历史规模、附件、加密异地副本、备份保留策略或生产 RPO/RTO。脚本只停止已确认归属的自有容器，保留现场；任何后续清理需先列出具体对象并确认。CI 只输出脱敏报告，不上传 dump、导出或秘密。
