# 16 日记导出界面交接

范围见 [16工单](../tasks/16-journal-export-ui.md)。从 `codex/tag-renaming` 的 `3957c0be510df833ff7c8a90ab4be521b653f0e0` 堆叠到 `codex/journal-export-ui`，依赖 [PR #16](https://github.com/GZY-q/LifeArchive/pull/16)；不自动合并前序交付。

## 使用与运行

登录后主导航“导出” → 默认仅活动日记，或勾选“包含回收站” → “生成导出文件” → 校验完成后“下载日记 ZIP”。包含所选日记全部修订、当前/历史引用原图、完整标签目录和哈希清单；未保存草稿、未关联上传、认证与配置不包含。ZIP未加密，请妥善保管；并不等于全库及原文件备份。

生成成功的链接属于当前选项和生成时快照。选项变化、重生成、离开页面或退出会话时撤销Blob URL；回到导出页必须重新生成。不自动生成/下载/重试，不把私密条件放入URL或浏览器持久化。正在生成可切回日记，原编辑器/草稿不重挂载。取消仅中止浏览器读取，服务端同步只读导出可能继续至完成或时限，不启动后台任务。

本片没有依赖、配置或数据库迁移，head仍 `0006_journal_pinning`，导出仍v4。已有Compose实例更新：

```bash
docker compose up -d --build --wait
```

本机在仓库根目录分别开两个终端（数据库/owner按README配置，不初始化或重置现有数据）：

```bash
cd apps/server
uv run --locked uvicorn life_archive.main:app --host 127.0.0.1 --port 8000
```

```bash
cd apps/web
npm run dev
```

默认5173代理8000。已有开发预览沿用 [18088](http://127.0.0.1:18088/)，API18884，私密启动说明见 `/Users/gede/.cache/lifearchive-tags-dev-qockdezn/HANDOFF.md`。不替预览owner导出私密档案或修改数据，不build覆盖18086所用旧dist。

网页超限时，使用原有CLI和全新绝对目标路径：

```bash
docker compose exec -T api python -m life_archive.cli export-journal --output /tmp/new-journal-export.zip
```

需要回收站时加 `--include-deleted`；已有目标必须拒绝，改用新路径。CLI保留0600、排他创建和失败残留；[格式文档](export-format.md)提供独立逐文件SHA-256核验。

## 实现与边界

- `journal/export.py` 的 `write_journal_archive` 是CLI和HTTP共享的快照/成员/校验入口。HTTP显式绑定认证owner，数量预检与数据读取同一独立只读REPEATABLE READ连接，不借用认证Session事务。CLI不使用网页限额，仍在成功返回前fsync。
- `journal/export_router.py` 的POST `/api/v1/journal-export` 严格JSON `{include_deleted?: boolean}`（默认false），复用owner/可信Origin/JSON/自定义头/CSRF/no-store。固定安全附件名，不接收owner、路径或文件名。服务端完整校验后才发送200 ZIP；失败仅通用JSON，无附件头和私密错误详情。
- 网页上限为1000篇所选日记、5000条所选修订、2000个目录标签、32MiB ZIP；计数超限或压缩字节溢出为413/export_too_large，不截断。30秒是通过缓冲写入/读取检查的协作式时限，每SQL最多3秒；不是硬实时中断。超时504/export_timeout，媒体/数据库/核验失败503/export_unavailable。
- 每API进程一个生成/ASGI响应名额，忙碌429/export_busy、Retry-After:5。不是分布式限制，多进程会分别占用内存；32MiB是ZIP长度上限，不是进程RSS上限，ZIP目录、清单和响应/Blob有额外开销。HTTP不落服务端文件，失败没有持久化工件，不自动清理任何既有数据。
- `api/client.ts` 仅新增每次调用可选Accept/timeout，原调用默认值保持；`api/export.ts`指定ZIP和45秒读取超时，校验响应类型/非空/32MiB。`ExportWorkspace`管理读取中止和Blob URL生命周期；AuthGate按需挂载它，常驻日记不重挂载，无写入/目录刷新。
- 生成时已经获授权的请求可能在会话撤销后完成，沿用现有认证边界；后续请求须重新认证。断网后没有可恢复下载任务，显式重试会读取新快照。

## 实际验收

2026-10-26，专用真实PostgreSQL `life_archive_tests`，凭据从私密连接文件注入 `TEST_POSTGRES_*`，未打印或提交；各用例迁移随机独立schema并保留，没有重置开发预览库。

在 `apps/server` 执行（先按README设置专用测试连接）：

```bash
uv run --locked pytest tests/journal/test_export_http.py tests/journal/test_export.py -q
uv run --locked ruff check src/life_archive/journal/export.py src/life_archive/journal/export_router.py src/life_archive/main.py tests/journal/test_export.py tests/journal/test_export_http.py
uv run --locked ruff format --check src/life_archive/journal/export.py src/life_archive/journal/export_router.py src/life_archive/main.py tests/journal/test_export.py tests/journal/test_export_http.py
```

- 25项通过，无跳过，其中6项HTTP、19项既有导出回归。验证活动/回收站策略、原文逐字节、置顶/名称历史、当前已解除关联的历史原图、清单全部哈希；对比全部应用表行证明只读。连接实测readonly/repeatable read/3秒SQL配置，既有双连接并发快照、CLI排他目标/残留/敏感信息回归保持。
- HTTP验证真实会话/Origin/JSON/自定义头/CSRF、严格布尔和未知字段、认证ID不回落到其他owner、数量/ZIP大小/协作超时/真实SQL取消、缺图/核验失败、同时请求拒绝与名额恢复。错误均无附件且不泄漏私密错误文本。
- 相关Ruff lint/格式与 `git diff --check` 通过。

在 `apps/web` 执行：

```bash
npm test -- src/export/ExportWorkspace.test.tsx
npm run typecheck
npm run lint
npm run format:check
```

- 4项通过：显式生成与默认范围/重新选项、ZIP/CSRF/45秒参数、下载链接撤销、同编辑器与草稿；离开时中止并忽略迟到响应；413/429/503/504/无效响应不提供下载、显式重试；401重新登录后草稿保持且不自动导出。
- 首次前端测试有1项因页面另有服务状态提示而定位不唯一，已将断言限定导出区域，4项复核通过。未用模拟ZIP声称浏览器下载文件内容已验收；实际ZIP内容由真实PG的HTTP测试核验。
- TypeScript、ESLint和Prettier检查通过。仅重启已核实归属的18884 API，18088首页、导出Vite模块和代理健康HTTP200；匿名导出401/no-store，不生成档案。18086 Caddy、18088 Vite进程和旧dist保持，未登录或操作预览owner数据/凭据/原图，用户`.DS_Store`保留。

未运行本机全量测试、build、浏览器/恢复/真机；Docker本机不可用。本片独立CI按PR触发，不能用上一片结果替代。07真机输入法仍待证据。

## 后续只规划

17可切“导出范围预检”：只读显示所选篇数/修订数与引用原图体积，说明预检和生成快照可能不同，最终限额仍在生成事务验证。先定义工单，不新增队列、导入、任意路径、删除、新闻或AI。
