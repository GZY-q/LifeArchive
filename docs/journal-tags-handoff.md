# 08 日记标签交接

本片范围见 [工单](../tasks/08-journal-tags.md)。分支 `codex/journal-tags` 从 `codex/editor-compatibility` 的 `1b0f169e65d855a20bdbacfb66d2489ab5d7ec30` 开始。此前 PR 仍按依赖待审；不自动合并。07 真机输入法矩阵没有新增人工证据，继续待验收。

## 使用与运行

登录后在编辑区创建/勾选标签，随日记保存；最多 20 个。编辑和修订历史显示标签；列表下拉框按一个标签筛选，切换筛选保留草稿。取消日记编辑不会删除已创建的目录标签。标签没有改名、删除或层级。归档搜索的标签条件留待后续。

现有 Compose 实例升级：

```bash
docker compose up -d --build --wait
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic current
```

head 为 `0004_entry_tags`。迁移新增 `tags`/`entry_tags`、owner 复合外键及修订 `tags` JSONB；旧修订得到 `[]`，不改写原文。本轮没有迁移用户已有实例或输入法测试库。不要对有数据的实例执行 downgrade。

本机新功能预览为 [18088](http://127.0.0.1:18088/)，独立数据库 `life_archive_tags_dev_023ff14a02`。账号凭据在本机 `/Users/gede/.cache/lifearchive-tags-dev-qockdezn/credentials.json`（0600），启动说明同目录 `HANDOFF.md`；不提交密码。已有 [18086](http://127.0.0.1:18086/) 保持输入法环境和旧静态产物。

## 代码入口与约定

- 后端：`journal/models.py`、`schemas.py`、`tags.py`、`tag_router.py`；正文与标签写入集中在 `service.py`。先完成 revision CAS，再替换关联并写修订，同事务提交；无效标签整体回滚。
- 创建重放对比 revision 1 的正文、日期和标签集合；后续编辑标签不使原请求失效。软删除请求仍不可复活。标签 owner 约束同时由服务和数据库保证。
- 前端：`api/tags.ts`、`journal/TagPicker.tsx`、`TagBadges.tsx`、`EntryForm.tsx`、`JournalWorkspace.tsx`、`draft.ts`。冻结创建请求包含 tag_ids；冲突重基保留草稿选择，列表切换取消旧请求。
- 导出：`journal/export.py` 写 [格式 v2](export-format.md)，`tags.json` 保存全部 owner 标签，当前/历史 JSON 保存各自标签。与原文处于同一只读快照。v1 已有文件仍可独立阅读/核验。
- 恢复脚本同步比较 Tag/EntryTag；合成夹具包括未使用标签、标签替换/清空、软删除关联与历史。同步了脚本，不等于本轮执行过完整恢复。

## 本轮验证边界

遵循用户“减少所有的测试行为，先开发功能”，仅执行：

- 真实 PostgreSQL：`tests/journal/test_tags.py` 和 `test_migrations.py`，5 项通过，覆盖标签保存/清空、首次请求重放、筛选/游标、revision 冲突原子性和迁移。
- 真实 PostgreSQL：导出完整元数据与并发快照的 2 项关键用例通过；`PortableComparisonTests` 2 项通过。
- 前端 `npm run typecheck`、`npm run lint` 通过；新增标签创建/冻结重试、筛选取消旧分页/保留草稿、仅标签变更识别共 3 项通过。
- 后端修改文件 Ruff 检查/格式检查通过；独立开发库升级到 `0004_entry_tags` 并初始化独立 owner。

未执行本机全量回归、真实浏览器演练、完整恢复演练或新一轮真机验收。CI 自动触发时按实际状态单独记录，不能引用旧 CI 当作标签功能已验证。

必要用例复核命令（PG 环境须安全注入 `TEST_POSTGRES_*`）：

```bash
cd apps/server
uv run --locked pytest -q tests/journal/test_tags.py tests/journal/test_migrations.py
cd ../web
npm run typecheck
npm run lint
npm test -- --run src/journal/JournalWorkspace.test.tsx src/journal/draft.test.ts -t 'creates and selects a tag|changes the tag filter|treats tag-only'
```

## 下一步

建议 09 做回收站查看与恢复：owner 软删除记录分页、按当前 revision 原子恢复、保留原 UUID 与历史、列表/搜索同步；不含永久清除。先补有界工单再实施。标签改名/删除和附件另切片，避免扩大本片。低成本模型接手时优先复用现有 CAS、鉴权、API client 和游标，不再搭建框架。
