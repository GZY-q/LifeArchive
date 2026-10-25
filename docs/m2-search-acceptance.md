# M2 第二片：归档搜索验收

验证日期：2026-10-25（Asia/Shanghai）。范围为 [03 工单](../tasks/03-archive-search.md)，基于 `codex/m2-calendar-days` 的 `54e0bd5`；PR #2、#3 尚未合并，本片沿用堆叠 PR。运行命令见 [搜索交接](m2-search-handoff.md)，下一步见 [待分配计划](next-steps.md)。

## 本机结果

| 检查 | 结果与覆盖 |
| --- | --- |
| 后端 `pytest -q --tb=short` | **151 passed，0 skipped**，专用 PostgreSQL 17.11；每项集成测试迁移随机 schema |
| 前端 `npm test` | **72 passed / 9 files** |
| 根目录 `python3 -m unittest discover -s tests -v` | **4 passed**，环境文件排他创建/权限/拒绝覆盖 |
| 后端 Ruff check + format --check | 从 `apps/server` 执行 `. ../../scripts ../../tests`，全部通过 |
| 前端 lint / format:check / typecheck / build | 全部通过；沿用现有锁文件与依赖 |
| Compose `--profile worker config --quiet` | 通过；本机没有 Docker Engine，完整容器运行单独由 CI 验证 |
| HTTP `scripts/smoke-journal.py` | 本机独立测试 owner/预览库通过；本机未执行 `--restart-postgres` |
| Chrome `scripts/smoke-browser.mjs` | 真实 Chrome + 当前 API 通过；日记、月历、归档各自验证 1440×1000 / 390×844，无横向溢出 |

总计 **227 项自动测试**。后端新增覆盖中文连续子串、英文大小写、`%`/`_`/斜杠/反斜杠/SQL 注入样式的字面文本、日期包含边界及年份 1/9999、补记、编辑与软删除、owner 隔离、同值排序分页、新记录插入、游标跨 owner/条件/接口拒绝、通用错误不回显、只读不写日记/修订、Origin/CSRF/会话和 no-store。

前端验证明确提交才请求、IME composition 不误提交、仅日期查询、已提交条件快照、分页与失败重试、会话重新验证后的 CSRF、迟到请求取消/忽略、401 私密 DOM 移除、明确退出清空、未确定创建 UUID 与 409 冲突跨归档导航保留。原文按纯文本显示，搜索词不写 URL、localStorage 或 sessionStorage。

HTTP 使用脚本自己的唯一关键词与记录，验证字面匹配/中英文/日期/分页/游标拒绝、编辑日期后命中变化、修订未写入、软删后不再命中。Chrome 通过录入→冲突处理→月历→归档搜索→未提交输入保持旧结果→删除→退出闭环；监测搜索网络请求确为 POST 且 URL 无查询参数。

首轮检查发现并修复了测试样本预期漏算其他含斜杠的记录、Testing Library 不支持的 `exact` role 参数及格式/未使用导入问题。最终上述命令均重跑通过。Ruff 必须从文档指定的 `apps/server` 运行以采用项目配置；从根目录误运行格式检查的结果不作为项目验收。

## CI

[PR #4](https://github.com/GZY-q/LifeArchive/pull/4) 的实现提交 `c3a44a96fe07a4e2ba7ce9fd1c374e74c8eea8da` 在 [CI run 40148000484](https://github.com/GZY-q/LifeArchive/actions/runs/40148000484) 完整通过：

- backend：151 项真实 PostgreSQL 测试、4 项环境保护测试及 Ruff 检查通过。
- frontend：72 项测试、lint、格式、类型与生产构建通过。
- compose：Docker 镜像构建、Caddy 路由、重复迁移、PG 重启迁移持久化、独立 worker 通过。HTTP 验证 PG 重启后会话、当前日记/修订、月历和搜索仍可读取；随后真实 Linux Chrome 完成日记/月历/归档闭环和桌面/手机尺寸布局验证。

后续证据提交只更新验收和 PR 链接，不修改实现或测试。审阅时同时查看 PR 最新提交的检查状态，不以历史绿色运行替代最新状态。

## 影响与限制

- 没有新依赖、环境变量、表、索引、迁移或后台任务；Alembic head 仍为 `0003_journal`，不执行回滚或重置。
- 本机预览沿用隔离的 `life_archive_preview` 数据库及 loopback 服务，未触碰其他日记；验收只软删自己创建的测试记录。没有删卷、覆盖 `.env`、重置 owner 或自动合并 PR。
- 字面子串搜索是基础归档能力，尚未验证多年大规模数据性能；游标不是跨请求快照。离开归档卸载结果，返回需要重新提交。
- 手机尺寸 Chrome 与模拟 composition 不等于真实 iOS/Android/系统输入法通过，详见待分配的 07 工单。新闻、AI、往年今日、导出与恢复演练未在本片实现。
