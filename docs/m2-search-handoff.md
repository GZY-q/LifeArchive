# M2 第二片：归档搜索交接

范围见 [03 工单](../tasks/03-archive-search.md)，验证见 [验收记录](m2-search-acceptance.md)，后续执行顺序见 [下一步计划](next-steps.md)。本片建立在 M1 与月历分片上；PR #2、#3 尚未合并时，本片 PR 以 `codex/m2-calendar-days` 为基线。先处理前序 PR，再复核差异并调整基线；不要重复合入同一批功能。

## 模块与约定

后端 `apps/server/src/life_archive/search/` 负责输入校验、绑定筛选条件的游标和 owner 范围的只读查询，响应复用 `journal.schemas.EntryPage`。前端 `apps/web/src/api/search.ts` / `src/search/` 负责同源请求、归档表单、已提交条件与结果；`AuthGate` 管理认证内导航和内存状态。既有日记事务、原文、修订和日期聚合不变。

接口是 `POST /api/v1/search`，不是 GET。关键词、日期和游标均放 JSON，请求需有效会话、可信 Origin 和 CSRF；不把搜索词放 URL、分析事件、日志或 localStorage/sessionStorage。服务端验证错误继续使用通用 422，SQL 使用绑定参数；禁止拼接关键词进 SQL。

关键词去首尾空白后按完整子串匹配，英文大小写不敏感，中文无需分词。空关键词可配日期范围查询；空关键词且无日期条件拒绝。`%` / `_` / 反斜杠 / 引号都是字面文本。日期边界包含两端，只解释 `entry_date`，与 UTC 创建时间无关。搜索当前未删除原文，不检索历史修订或回收站。

独立游标绑定 owner、规范化关键词和日期条件的摘要，不含原始关键词；不得和普通日记或日期详情游标互换。翻页按日记日期、创建时间、ID 降序继续。它不是数据库快照，记录在两次请求间被编辑或改日期时可能移动；重新搜索获得当前结果。

前端手动提交；修改输入时，旧结果继续标注自己的已提交条件。翻页和错误重试使用该快照。离开归档会中止请求并移除结果，返回后保留同页输入、由用户再次提交；401 移除全部私密 DOM，显式退出清空搜索输入。日记组件继续常驻于认证内，草稿、创建幂等键与待处理冲突不会因查看归档丢失。

当前实现没有新增依赖、迁移、配置项、数据库扩展、搜索历史表或后台服务。前置通配的字面子串匹配可能扫描 owner 的多条记录；不宣称几十年数据已达到全文索引性能。后续先用实际中文样本测量，再单独决定 pg_trgm 或分词方案。

## 运行与验证

已有 M1/M2 实例从仓库根目录执行：

```bash
docker compose up -d --build --wait
docker compose exec -T api alembic current
```

迁移 head 仍为 `0003_journal`。新实例按根 README 首次初始化环境、迁移和 owner；不重置已有 owner 或数据库。登录后选择“归档”，输入关键词或日记日期范围并点“搜索日记”。

从 `apps/server`，私密注入独立 `TEST_POSTGRES_{HOST,PORT,USER,PASSWORD,DB}` 后：

```bash
uv run --locked pytest
uv run --locked ruff check . ../../scripts ../../tests
uv run --locked ruff format --check . ../../scripts ../../tests
```

从 `apps/web`：

```bash
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
```

HTTP / Chrome 脚本沿用 [M1 隔离项目启动顺序](m1-handoff.md#精确运行与测试)，扩展搜索检查：

```bash
python3 scripts/smoke-journal.py --base-url http://127.0.0.1:18080 --allow-test-writes --restart-postgres
node scripts/smoke-browser.mjs http://127.0.0.1:18080
```

只用于显式隔离测试项目和临时 owner；脚本会创建并软删自己的测试记录。Chrome 要求空的活动日记列表，使用独立临时 profile。不要对正式数据实例运行。

接手模型请先看下一步计划与当前 PR 状态，选择一张明确分配的工单。往年今日、导出、恢复演练、真实输入法矩阵都只是计划，不应在搜索修复中顺手实现。
