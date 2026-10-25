# M2 第三片：往年今日验收

验证日期：2026-10-25（Asia/Shanghai）。范围为 [04 工单](../tasks/04-on-this-day.md)，基于搜索提交 `409e6875bb6dfc507c0b0319337284e2d750ca51`，不含导出或新闻/AI。精确命令见 [交接](m2-on-this-day-handoff.md)。

## 本机验证

| 检查 | 实际结果 |
| --- | --- |
| 后端 `pytest -q --tb=short` | **184 passed，0 skipped**；独立 PostgreSQL 17.11，测试随机 schema |
| 前端 `npm test` | **97 passed / 11 files** |
| 根目录环境保护 unittest | **4 passed** |
| Ruff check / format --check | 从 `apps/server` 检查 `. ../../scripts ../../tests`，通过 |
| 前端 lint / format:check / typecheck / build | 通过，无依赖或锁文件变化 |
| Compose `--profile worker config --quiet` | 通过；本机没有 Docker Engine，完整容器验收由 CI 独立运行 |
| HTTP smoke | 通过，使用隔离预览库和测试 owner；本机未执行数据库重启参数 |
| 真实 Chrome smoke | 通过；日记/月历/归档在 1440×1000 和 390×844 无横向溢出，另检查往年区域的桌面/手机尺寸截图 |

总计 **285 项自动测试**。新增后端测试覆盖过去/同年/未来年份、严格月日和世纪闰年、年份 1/9999、补记日期与创建 instant 分离、owner/软删除、编辑日期变化、keyset 同值排序/插入较新记录、跨日期/owner/接口游标、默认日期跨 UTC 日界及跨午夜分页、只读原文/修订不变、认证失效和 no-store 通用错误。

前端新增测试覆盖显式展开才读取、owner 时区默认日期、完整年份和原文安全渲染、接口响应日期/年份/月日校验、第一页/分页重试、日期切换及刷新时取消迟到请求、折叠/导航取消、首屏/分页 401 卸载全部私密 DOM、重新登录草稿恢复及显式退出清空。既有日记 UUID、409 冲突和忙时导航测试同时通过。

HTTP 复用脚本自己的两条 2000-02-29 日记：参考 2040-02-29 验证过去闰日、分页及游标隔离；将一条改为 1999-12-31 后，参考 2000-12-31 可读取新原文，历史修订保持不变；软删后回看不可见。Chrome 验证 2001-02-03 原文在参考 2026-02-03 时出现、同年排除、切日/刷新/折叠/删除生效、日记草稿和原有搜索流程不回归。

首轮独立 HTTP 脚本在宿主 Python 3.9 因 `datetime.UTC` 不可用而失败，已改用兼容的 `timezone.utc` 并重跑 HTTP/Chrome 通过；后端仍使用项目锁定的 Python 3.12。该脚本的局部 Ruff UP017 说明仅保留旧宿主命令兼容，不修改应用运行版本。

## CI

[PR #5](https://github.com/GZY-q/LifeArchive/pull/5) 的实现提交 `767a4c337b6432af80df214acd21dd0d8299bc44` 已在 [CI run 40186738386](https://github.com/GZY-q/LifeArchive/actions/runs/40186738386) 完整通过：

- backend：184 项真实 PG 测试和 4 项环境保护测试，Ruff 检查通过。
- frontend：97 项测试、lint、格式、类型、生产构建通过。
- compose：Docker 构建、Caddy 路由、重复迁移、PG 重启后的迁移/会话/日记/搜索/往年回看读取、独立 worker 通过；真实 Linux Chrome 完成展开/切日/刷新/折叠、删除与退出，以及日记/月历/归档桌面和手机尺寸回归。

首次后端 CI 在安装 pytest 时遇清华镜像 HTTP 403，未进入测试；只重试失败任务后安装和全套验收通过，没有修改依赖源、版本或锁文件。后续证据提交只更新文档与 PR 链接；审阅时同时核对 PR 最新 head 的检查状态。

## 影响与限制

无新增依赖、配置、迁移、索引、后台任务或数据写接口；head 仍为 `0003_journal`。未覆盖现有 `.env`，未重置 owner、回滚迁移、删库或删卷，保留用户 `.DS_Store` 修改。

按月日过滤目前没有专用表达式索引，未证明多年大档案性能；分页为继续位置，跨请求编辑可能移动记录。真实设备/系统中文输入法仍未验证，桌面 Chrome 手机尺寸检查不替代该矩阵。导出、备份、恢复演练、新闻/AI、标签和媒体不在本片。
