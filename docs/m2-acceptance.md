# M2 第一片验收记录

验证日期：2026-10-25（Asia/Shanghai）。范围为 [tasks/02-calendar-days.md](../tasks/02-calendar-days.md)，仅月历与日期详情；不是完整 M2。

## 本机检查

沿用 M1 的 Python 3.12.14 / uv 0.12.17 / Node 24.19.0 / npm 11.17.0 / PostgreSQL 17.11，没有新增依赖或全局安装。真实测试库与预览库分开，连接密码与 owner 密码仍在仓库外私密文件。

| 检查 | 结果 |
| --- | --- |
| 根目录 `python3 -m unittest discover -s tests -v` | 4 项通过 |
| `apps/server` 配置独立 TEST_POSTGRES_* 后 `uv run --locked pytest -q` | 111 项通过，真实 PG，零跳过；新增 33 项日期 API 回归 |
| `apps/server` `uv run --locked ruff check . ../../scripts ../../tests` | 通过 |
| `apps/server` `uv run --locked ruff format --check . ../../scripts ../../tests` | 通过 |
| `apps/server` `uv lock --check --offline` | 40 个解析包，锁一致 |
| `apps/web` `npm run lint` / `npm run format:check` / `npm run typecheck` | 通过 |
| `apps/web` `npm test` / `npm run build` | 55 项通过；新增 28 项日期/API/交互回归，构建通过 |
| Compose standalone `compose --profile worker config --quiet` | 通过；本机无 Docker Engine |
| `node --check scripts/smoke-browser.mjs` 与该文件 Prettier check | 通过 |
| `git diff --check` | 通过 |

合计 **170 项测试**（111 后端 + 55 前端 + 4 环境保护），不是重复累计多轮执行。覆盖日期与 UTC 创建时间分离、补记、同日多条、月份/闰年/年份 1–9999 边界、权限/删除、日期游标绑定、修改日期后计数变化，以及草稿/幂等键/冲突状态跨视图保留、请求竞态、分页重试和 401 私密 DOM 清除。

恢复本机预览时首次 PG 启动使用了默认端口，导致连接检查与集成测试失败；恢复显式 loopback 25432 与 UTC 参数后，以上检查和 HTTP 验收通过。没有为解决连接问题删除或重建数据库；本机重启说明已另存修正版。

## 实际链路

`scripts/smoke-journal.py` 对 Caddy → Uvicorn → 真实 PostgreSQL 通过：保留原 M1 认证/CSRF/幂等/修订/冲突/撤销验收，并新增闰日计数、同日分页、跨日游标拒绝、原文一致、跨月/年改日期、软删除后计数及单日内容更新。脚本按基线比较，只软删除本次创建的两个测试记录。

`scripts/smoke-browser.mjs` 在真实 Chrome 通过：原 M1 录入/IME/会话轮换/409/历史闭环、查看月历后返回继续未保存的原文和日期、补记计数、单日原始 Markdown、空日、删除后刷新计数和退出。日历与日记均在桌面 1440×1000、手机尺寸 390×844 无水平溢出；截图已检查。原文中的 HTML 未执行，localStorage/sessionStorage 为空。

本机仍是原生预览链路，数据库重启持久化的容器验证由 PR CI 执行；结果待实际完成后补入，不能以本机检查代替。

## 迁移与边界

- 无新增迁移、表、依赖或配置项；head 仍为 `0003_journal`。不需要重置 owner 或业务数据。
- M1 的 PR #2 尚未合并时，本 PR 基于 M1 分支；主分支上线需先处理依赖 PR 并复核差异。
- 日详情仅包含日记；搜索、往年今日、标签/附件、新闻、AI、备份都未实现。
- Chrome composition 和手机尺寸模拟不等于真实系统输入法/软键盘矩阵；此人工验收限制继续保留。
