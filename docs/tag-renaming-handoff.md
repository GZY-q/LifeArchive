# 15 标签改名交接

范围见 [15工单](../tasks/15-tag-renaming.md)，交付 [PR #16](https://github.com/GZY-q/LifeArchive/pull/16)。从`codex/markdown-preview`的`0a1a9bc938ce50431f5d412ccd9a75cbc72a56bf`堆叠到`codex/tag-renaming`，依赖 PR #15；前序PR不自动合并。保留现有用户数据与18086旧输入法环境，07真机矩阵仍待人工证据。

## 使用和运行

主导航“标签”读取完整私密目录，选择一个标签编辑、显式保存。标签ID和关联稳定，当前日记显示新名称；历史版本显示保存时名称，不回写旧快照。改名不产生日记修订，不改变原文、日期、置顶、附件或创建请求UUID。

本片无新依赖、配置或数据库迁移，head仍`0006_journal_pinning`、导出v4。已有Compose实例在仓库根目录更新：

```bash
docker compose up -d --build --wait
```

本机两个终端分别启动API与前端（数据库/owner按根README预先配置，不重置已有实例）：

```bash
cd apps/server
uv run --locked uvicorn life_archive.main:app --host 127.0.0.1 --port 8000
```

```bash
cd apps/web
npm ci --registry=https://registry.npmmirror.com
npm run dev
```

默认前端5173代理API8000；当前开发预览沿用[18088](http://127.0.0.1:18088/)，API18884，私密启动说明在`/Users/gede/.cache/lifearchive-tags-dev-qockdezn/HANDOFF.md`。不要对预览owner实际改名/改密或撤销会话，不build覆盖18086所用旧dist。

## 接口和数据边界

`PATCH /api/v1/tags/{tag_id}`严格JSON `{name,expected_name}`，返回现有`{id,name,created_at}`。name复用trim+NFC、NFKC+casefold唯一键与1–40字符规则；expected_name为读取的原样名称，1–40字符不规范化。复用owner/Origin/JSON/CSRF/no-store。

事务内锁定owner标签并比较expected_name；不存在/越权404，旧名称409/tag_conflict，规范唯一键被其他标签占用409/tag_name_taken。ID/created_at不变，无删除/合并/层级。唯一约束处理同时创建/改名，失败回滚；相同名称且expected_name匹配为无操作成功。expected_name并非单调版本号，无法发现A→B→A循环，这是无迁移的明确限制。

改名仅更新目录name/name_key。当前读取与导出tags.json用新名，旧revision JSONB保留旧名；之后日记保存/恢复快照使用当时可见目录名。创建重放比较revision1标签ID集合，所以仍可成功；同一标签ID在历史中出现不同名称为预期。导出仍来自同一只读快照，格式/路径/哈希不变。

前端忙碌时锁导航/退出和重复操作；IME组合输入不提交。409或网络/5xx结果不确定时保留输入并停止直接重试，先重新读取目录再显式编辑；不把不确定请求当成功。目录核对/改名通知AuthGate刷新常驻日记目录与列表，标签筛选ID不变，不重挂载编辑器或重置原文/图片/冻结UUID/409。归档再次进入重读目录，仍须显式搜索，不自动重放私密查询。

## 实际检查

2026-10-26，在本机专用 `life_archive_tests` PostgreSQL 数据库运行；连接凭据仅从私密连接文件注入 `TEST_POSTGRES_*`，未打印或提交。每个用例迁移随机独立 schema，并保留用于排查，没有重置开发预览库。

后端，在 `apps/server` 执行（先按根 README 配置专用测试库的 `TEST_POSTGRES_*`）：

```bash
uv run --locked pytest tests/journal/test_tag_renaming.py -q
uv run --locked ruff check src/life_archive/journal tests/journal/test_tag_renaming.py
uv run --locked ruff format --check src/life_archive/journal tests/journal/test_tag_renaming.py
```

- 4 项真实 PostgreSQL 测试通过，无跳过。覆盖 NFC/NFKC 唯一性、expected_name 不归一化和严格类型、未知/越权一致 404、真实会话及 Origin/JSON/自定义头/CSRF、同标签并发 CAS、不同标签并发抢占名称后的事务回滚。
- 对比改名前后的 Entry/EntryTag/EntryRevision 行，证明没有日记写入；验证原文逐字节、ID/created_at、创建 UUID 重放、当前与历史标签、导出 v4 和后续恢复快照。
- Ruff lint 与格式检查通过（12 个文件）。

前端，在 `apps/web` 执行：

```bash
npm test -- src/tags/TagsWorkspace.test.tsx
npm run typecheck
npm run lint
npm run format:check
```

- 7 项测试通过。覆盖显式保存/IME、写入时导航与退出禁用、同一编辑器节点/原文/已选标签与筛选 ID/冻结创建请求保留，以及改名后的目录和列表刷新。
- 名称冲突、并发冲突、断网、503 和无效成功响应均要求重新读取目录、显式重新编辑，保留用户输入；组件卸载后的迟到响应不更新目录或父组件状态。
- TypeScript、ESLint 与最终 Prettier 检查通过；新增测试首次格式检查发现排版问题，定向格式化该文件后复核通过。`git diff --check` 通过。

只重启已核实属于本项目的 18884 API。18088 首页、标签管理 Vite 模块和代理健康接口均 HTTP 200；未登录或替 owner 修改标签、密码、会话、日记或原图。18086、旧 dist 和用户 `.DS_Store` 保留。

未运行本机全量测试、build、浏览器/恢复演练或真机输入法验收；Docker 在本机不可用，Compose 验收由本片 PR 的独立 CI 执行，不能用上一片 CI 结果替代。07 真机矩阵继续待证据。

## 后续接手

下一片只规划16“日记导出界面”：复用现有只读CLI/导出服务与鉴权，先定义响应大小、超时、失败工件保留、当前/历史原图范围，不新增队列或导入器。标签/媒体永久清除仍需单独保留策略和用户确认，不顺手加入。低成本模型继续复用现有事务、客户端和草稿边界，不重搭框架、不引入新闻/AI。
