# M2 第三片：往年今日交接

本片 [PR #5](https://github.com/GZY-q/LifeArchive/pull/5) 实现 [04 工单](../tasks/04-on-this-day.md)，证据见 [验收记录](m2-on-this-day-acceptance.md)。基线是搜索 PR #4 的 `409e6875bb6dfc507c0b0319337284e2d750ca51`，分支 `codex/m2-on-this-day`；前序 PR #2–#4 仍待合入，保持依赖顺序并在上游合入后复核 base/差异/CI，不自动合并。

## 模块和固定语义

- `apps/server/src/life_archive/timeline/on_this_day.py`：owner 时区的默认日期、过去年度同月同日只读查询和游标；`router.py` 注册 `/api/v1/on-this-day`，`schemas.py` 声明独立游标，复用已有 DayResponse/EntryPage。
- `apps/web/src/api/calendar.ts`：显式参考日期和分页请求，验证返回日期、过去年份和相同月日；`calendar/OnThisDay.tsx`：折叠区域及分页结果；`CalendarWorkspace.tsx` 传选中日期和刷新序号。
- 读取当前 owner 未删除原文，条件是 `entry_date` 年份小于参考年份且月日相同，与 UTC 创建时间无关。2 月 29 日不挪到相邻日期；参考年 1 返回空，支持完整年份 1–9999。
- API 的 `date` 可省略，此时只使用当前 UTC instant 在 owner IANA 时区下的日期；响应返回实际采用日期。客户端及后续分页始终显式传日期，避免跨午夜改变条件。
- 分页按日记日期、创建时间、ID 降序；`on-this-day-v1` 游标绑定 owner 和完整参考日期，拒绝跨日期/owner/日记/日期详情/搜索游标。它只表示继续位置，不保证跨请求快照。
- 不写日记或修订，不检索旧修订，不建立派生表。会话必需、响应 no-store、错误通用 422；GET 不增加 CSRF 写操作路径。

## 前端状态边界

进入日历时“往年这一天”默认收起，只有展开才读取。展开后变更选中日期或点击“刷新日历”时，保留展开意图；以日期和刷新序号重挂载结果，取消旧请求并从第一页读取。分页失败保留已读条目，用相同日期/游标重试。

收起或离开日历即取消请求、卸载结果；返回日历仍需展开。401 卸载所有私密 DOM，显式退出清空回看状态。复用现有日记常驻组件，草稿、待确认创建 UUID、冲突状态和写入时导航保护继续有效。完整日期和原始 Markdown 按纯文本显示，无自动提醒、改写或外部 AI 调用。

## 精确运行和验证

已有 M1/M2 实例从仓库根目录执行：

```bash
docker compose up -d --build --wait
docker compose exec -T api alembic current
```

head 仍为 `0003_journal`；本片无新配置、依赖、表、索引或迁移。新实例按根 README 初始化环境、迁移和唯一 owner。登录后选择“日历”，选择参考日期，再点“展开往年这一天”。例如原文日期为 2000-02-29，参考 2024-02-29 可看到该文；参考 2000-02-29 或 2024-02-28 不会显示它。

从 `apps/server` 执行，先私密注入专用 `TEST_POSTGRES_{HOST,PORT,USER,PASSWORD,DB}`：

```bash
uv run --locked pytest
uv run --locked ruff check . ../../scripts ../../tests
uv run --locked ruff format --check . ../../scripts ../../tests
```

从 `apps/web` 执行：

```bash
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
```

根目录 `python3 -m unittest discover -s tests -v` 验证环境文件保护。按 [M1 隔离实例流程](m1-handoff.md#精确运行与测试) 建立专用项目、临时 owner 并私密设置 `LIFEARCHIVE_SMOKE_PASSWORD` 后执行：

```bash
python3 scripts/smoke-journal.py --base-url http://127.0.0.1:18080 --allow-test-writes --restart-postgres
node scripts/smoke-browser.mjs http://127.0.0.1:18080
```

脚本只用于 loopback 隔离测试项目；HTTP 仅编辑和软删自己创建的两条合成记录，Chrome 要求活动日记为空，不能为满足前置条件删除已有日记。可设置 `LIFEARCHIVE_BROWSER_ARTIFACT_DIR` 为仓库外新目录保存合成数据截图。

下一张建议任务是 [05 日记导出](../tasks/05-journal-export.md)，本片未实施。完整顺序和接手提示词见 [下一步](next-steps.md)。仍需独立恢复演练、真实系统输入法矩阵、M1 标签/附件等后续切片；这些缺口及生产备份未因日记侧 M2 三片完成而消失。
