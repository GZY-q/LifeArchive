# M2 第一片：月历和日期详情交接

范围严格对应 [工单](../tasks/02-calendar-days.md)，不是完整 M2。沿用 [M1 认证与日记约定](m1-handoff.md)，实际验证见 [验收记录](m2-acceptance.md)。M1 的 PR #2 尚未合并时，本片分支/PR 以 `codex/m1-secure-journal` 为基线；先合并依赖 PR 后，再核对本片差异并改为以 main 为基线。不要把两个 PR 的功能重复提交。

## 实现入口与约定

| 路径 | 职责 |
| --- | --- |
| `apps/server/src/life_archive/timeline/` | 两个只读接口、月历聚合和响应 schema |
| `apps/server/tests/timeline/` | 真实 PG 的日期、权限、分页与计数回归 |
| `apps/web/src/calendar/` | 纯公历日期运算、响应式月历与只读日期详情 |
| `apps/web/src/api/calendar.ts` | 同源请求与月份/日期/计数的运行时响应校验 |
| `apps/web/src/auth/AuthGate.tsx` | 认证内导航、保留日记工作区、401 时清除私密 DOM |
| `scripts/smoke-journal.py` | HTTP 月历/单日分页、日期移动、删除与数据库重启 |
| `scripts/smoke-browser.mjs` | 草稿跨视图、补记计数、原文/空日及桌面/手机尺寸 |

月历对 `entries` 按 owner、未删除、`entry_date` 范围筛选并 GROUP BY。月末使用公历闭区间，避免 9999 年 12 月加一月溢出。日详情复用 journal 的 `list_entries`，传入固定日期；继续游标与日期绑定，不能跨日复用。不添加时间推断、新闻空字段、缓存表或后台任务。

前端日期运算使用年/月/日整数与公历规则，不能用 `new Date('YYYY-MM-DD')` 再取本地日期，也不能落入 JavaScript 0–99 年构造偏移。初始今天通过 owner IANA 时区计算。切换到日历后保留原日记组件及内存草稿/冲突状态；写请求忙时禁止切换。日历每次进入重新读取，手动刷新会同时更新月历计数和日期详情。删除、日期修改和其他窗口写入不会主动推送，需刷新。

未认证时两个新接口均拒绝访问；所有响应 no-store。日详情显示原始 Markdown 文本，不执行 HTML。401 沿用 AuthGate 流程，移除两个视图的私密 DOM；保留同页草稿供同一 owner 重新登录继续。

## 运行与验证

没有新增依赖、配置项或数据库迁移；已有 M1 实例可直接重新构建：

```bash
docker compose up -d --build --wait
docker compose exec -T api alembic current
```

迁移版本仍是 `0003_journal`。新实例先按根 README 初始化环境、执行 `alembic upgrade head` 和首次 owner CLI；不要为更新月历重置 owner、删库或删卷。登录后选择“日历”，可以切换月份、跳转日期、查看同日原文并加载更多。

后端检查从 `apps/server` 执行；使用独立真实 PG 测试连接 `TEST_POSTGRES_{HOST,PORT,USER,PASSWORD,DB}`，密码私密注入，不能写入命令参数/日志：

```bash
uv run --locked pytest
uv run --locked ruff check . ../../scripts ../../tests
uv run --locked ruff format --check . ../../scripts ../../tests
```

前端从 `apps/web` 执行：

```bash
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
```

完整容器验收沿用 [M1 隔离启动顺序](m1-handoff.md#精确运行与测试)：先在独立 `life-archive-smoke` 项目初始化临时 owner，再运行这两个扩展后的脚本。不要对正式数据实例执行验收写入。

```bash
python3 scripts/smoke-journal.py --base-url http://127.0.0.1:18080 --allow-test-writes --restart-postgres
node scripts/smoke-browser.mjs http://127.0.0.1:18080
```

HTTP 脚本按日期读取基线，只软删除自己创建的测试记录；Chrome 要求空的活动日记列表和独立临时 profile。两者都要求测试项目名、临时 owner 密码与 loopback 入口。Chrome 使用 Node 24 和已安装 Chrome，可通过 `CHROME_BIN` 指定；截图保存在私密临时目录，不进入 Git。

## 接手边界

搜索、往年今日、标签、附件、恢复/永久删除、新闻、AI 和备份都不在本片。真实系统中文键盘矩阵仍是 M1 的人工验证限制；模拟 composition 和手机尺寸不代表全设备通过。后续模型先检查分支/PR 依赖及验收记录，再执行明确分配的小工单，复用现有日期 API、权限依赖和原文分页。
