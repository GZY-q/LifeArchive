# 09 回收站交接

实现范围见 [09 工单](../tasks/09-journal-trash.md)。分支 `codex/journal-trash`，基于 `codex/journal-tags` 的 `a323f7d14a943bf1278330ab93870742974504f0` 堆叠交付。前序 PR 依然按依赖审阅，不自行合并。07 真机输入法矩阵仍待证据，不作为本功能完成声明。

## 功能与运行

登录后打开“回收站”，查看已删除日记的原文、日期、标签及删除时间，逐篇恢复。恢复保留原 ID、原文、标签、创建时间和历史，并新增一次修订；恢复后返回日记列表可见，月历/搜索等在重新读取时包含该记录。切换导航与恢复不会清空内存草稿。没有永久清除、自动清空或批量恢复。

已有 Compose 实例从仓库根目录运行：

```bash
docker compose up -d --build --wait
docker compose exec -T api alembic current
```

本片没有新迁移或依赖；从标签版本升级时 head 仍为 `0004_entry_tags`。更早版本先按根 README 显式 `docker compose exec -T api alembic upgrade head`，不降级或重置数据。

本机继续使用 [18088 预览](http://127.0.0.1:18088/)，数据库和 owner 沿用上一片，不删除或重建数据。私密启动说明 `/Users/gede/.cache/lifearchive-tags-dev-qockdezn/HANDOFF.md`，凭据同目录 `credentials.json`（0600）。18086 输入法测试环境保持不动。Vite 开发预览不等于生产发布。

## 核心约定与代码入口

- `journal/trash.py`：回收站 owner 读取和 `trash-v1` 游标，按 `(deleted_at,id)` 降序；与日记/搜索游标隔离，不承诺跨请求快照。当前没有新增回收站专用索引或大规模性能承诺。
- `journal/trash_router.py`：`GET /api/v1/trash`，limit 1–100；每项为 EntryResponse + `deleted_at`，会话与 no-store 沿用现有机制。
- `journal/router.py`：`POST /api/v1/entries/{id}/restore {expected_revision}`，严格正整数/未知字段拒绝，可信 Origin + CSRF。
- 恢复 CAS 同时匹配 owner、已删除状态、revision；成功同事务清空 deleted_at、递增 revision、写 UTC updated_at 和原文/日期/标签快照。未知/外部 owner 404，已活动或版本变化 409，不会因旧恢复请求复活后来再次删除的版本。
- 软删除期间普通读取、编辑、历史和创建重放仍为 404；恢复后原请求可按 revision 1 匹配同一 UUID，历史重新可读。导出仍为 v2；默认只含活动记录，include_deleted 含全部，恢复不改变格式。
- `api/trash.ts`、`trash/TrashWorkspace.tsx`：原文纯文本显示、分页取消/去重、恢复操作互斥。409 或网络不确定保留条目、阻止直接重复恢复并要求刷新核对；不把请求失败当作未写入。
- `auth/AuthGate.tsx`：回收站导航和全局写入保护。`JournalWorkspace.refreshVersion` 仅刷新列表，不重挂编辑器或重置草稿/冻结创建请求/冲突面板。日历和归档离开后卸载，再进入重新读取。

## 必要检查

按用户“减少所有的测试行为，先开发功能”，仅新增少量关键用例，不运行本机全量回归、浏览器演练、完整恢复演练或新真机验收。

后端已执行：`tests/journal/test_trash.py` 真实 PostgreSQL **4 项通过**（0.50 秒），包括数据/历史/UUID保留、恢复后活动视图、分页/owner/游标隔离、重复/旧恢复拒绝及并发仅一次修订。限定修改文件 Ruff 检查和格式检查通过。

前端 `npm test -- --run src/trash/TrashWorkspace.test.tsx` **2 项通过**：冻结 UUID/正文/标签草稿跨回收站恢复保留、CAS 请求与全局写锁/列表刷新，以及 409/网络不确定结果要求刷新核对。`npm run typecheck`、`npm run lint` 通过，修改文件已格式化。只读子代理审查还修正了恢复后列表刷新失败继续使用旧游标的问题；首屏失败只提供首屏重试，不影响编辑器状态。

已复用原开发库和 owner，仅重启开发 API 加载本片代码，18088 健康接口正常、未认证回收站为 401。没有对预览库执行删除/恢复测试操作，也没有迁移或重置数据。不要引用标签提交的 CI 结果替代本片证据。

后续只读查询确认：提交 `7e5a4ff88e1f06c44d9da884bb2d8b3104ef5e21` 的 [自动 CI 40214450410](https://github.com/GZY-q/LifeArchive/actions/runs/40214450410) 已成功。本机未追加全量运行；此结果只属于09，不代表10标签筛选。

最小复核命令（PG 环境通过私密配置注入，缺配置的 skip 不等于通过）：

```bash
cd apps/server
uv run --locked pytest -q tests/journal/test_trash.py
cd ../web
npm run typecheck
npm run lint
npm test -- --run src/trash/TrashWorkspace.test.tsx
```

## 下一片建议

10 建议扩展归档标签条件：在现有 POST `/search` JSON 中加入单标签，与原文关键词和日记日期 AND；游标摘要绑定标签，前端复用现有目录，查询不放 URL。先写有界工单再实施；不提前开发新闻/AI或附件。私密附件需要授权存储与导出/备份一致性，应单独切片。
