# Task M2 第三片 — 往年今日

状态：用户要求继续后，本轮分配实施；一张工单对应一个 PR。2026-10-25 核对 PR #2–#4 尚未合入，本轮沿用既有堆叠交付，从 `codex/m2-archive-search` 的 `409e6875bb6dfc507c0b0319337284e2d750ca51` 新建 `codex/m2-on-this-day`，PR base 为搜索分支。按 [实施顺序](../docs/next-steps.md) 处理前序依赖，不自动合并。本片补齐只读日期回看，不创建新存储或后台任务。

## 固定接口与语义

- `GET /api/v1/on-this-day?date=YYYY-MM-DD&limit=20&cursor=...`，返回 `{date:"YYYY-MM-DD",entries:{items:[EntryResponse],next_cursor:null}}`。
- `date` 必须是严格公历日期，年份 1–9999；省略时使用当前 UTC instant 在 owner IANA timezone 下的本地日期。响应必须返回实际采用的日期。前端与继续分页都显式传回该日期，防止跨午夜改变查询。
- 只读取 `entry_date` 的年份 **小于**选中年份、月日完全相同的活动日记。选中年份和未来年份均不返回；选中年份为 1 时返回空列表。判断不依赖 `created_at` 或数据库服务器时区。
- 2 月 29 日仅命中以前年份真正的 2 月 29 日，不移到 2 月 28 日或 3 月 1 日。2 月 28 日也不包含闰日。
- 复用 session/owner 依赖；所有 SQL 带 owner 和 `deleted_at IS NULL` 条件，响应 no-store，未登录 401，日期/游标非法时通用 422。
- `limit` 为 1–100，默认 20；游标最长 2048。按 `(entry_date DESC,created_at DESC,id DESC)` keyset 分页。版本化游标绑定接口类型、owner 和本次参考日期；拒绝跨日期、跨 owner、journal/day/search 游标混用。
- 分页沿用现有“继续位置”语义，不宣称跨请求数据库快照。刷新从第一页开始；读取不修改原文、修订或日期。

## 前端范围

在现有日期详情下增加“往年这一天”只读区域，显示完整年份、原始 Markdown、空态、失败重试和加载更多。区域首次展开才读取；参考日期使用当前选中日期，不使用创建日期。切换日期取消/忽略旧响应并清空旧分页，手动刷新重新读取已展开区域。

沿用原生文本渲染和现有认证失效流程。切换日记/月历/归档仍保留内存草稿、未确定创建请求与冲突状态；写操作忙时保留现有导航保护。401 移除所有私密 DOM，显式退出清空回看数据。

## 实现入口

- 后端：`apps/server/src/life_archive/timeline/{router,schemas,service}.py`；复用 `journal` 响应和 keyset 约定，不把当前日列表的过滤条件偷偷改成往年查询。
- 前端：`apps/web/src/api/calendar.ts`、`calendar/CalendarWorkspace.tsx`、`calendar/DayEntries.tsx`；必要时新增独立 `calendar/OnThisDay.tsx`，沿用 `calendar/dates.ts` 公历运算。
- 测试：`apps/server/tests/timeline/`、相邻前端测试及现有 HTTP/Chrome smoke。文档更新 API contract、README、M2 交接和验收。
- 无新增依赖、环境配置、数据库表、迁移或索引。若实测性能要求索引，记录数据和后续工单，不能直接扩大本片。

## 验收与精确检查

真实 PostgreSQL 覆盖：多年同月同日、同年/未来年排除、补记与创建时间不同、owner/软删除隔离、2 月 29 日与世纪闰年、年份 1/9999、空日、分页排序同值以及游标混用。冻结当前 instant，验证 owner 两个跨 UTC 日界时区的默认日期；API 不依赖机器本地时区。

前端覆盖：展开读取、日期切换竞争、分页/重试、原文安全显示、跨视图草稿和 401；Chrome 验收桌面及手机尺寸回看，不宣称真机输入法通过。

从 `apps/server` 运行下列命令；真实 PG 使用独立 `TEST_POSTGRES_{HOST,PORT,USER,PASSWORD,DB}` 配置，秘密私密注入。缺少连接而跳过不是通过。

```bash
uv run --locked pytest
uv run --locked ruff check . ../../scripts ../../tests
uv run --locked ruff format --check . ../../scripts ../../tests
```

从 `apps/web` 执行 `npm run lint`、`npm run format:check`、`npm run typecheck`、`npm test`、`npm run build`。按 [M2 隔离验收](../docs/m2-handoff.md#运行与验证) 启动专用项目和临时 owner，再运行扩展后的 `scripts/smoke-journal.py`、`scripts/smoke-browser.mjs`；不能向真实日记库写验收数据。

交付单个 PR、实测结果、精确本机运行说明和 M2 尚缺项。明确排除：新闻/AI、随机回忆、周年提醒、跨年同一周匹配、日记改写、标签/媒体、搜索排名、编辑器替换、导出/备份。
