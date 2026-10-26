# 12 日记置顶交接

范围见 [12工单](../tasks/12-journal-pinning.md)。分支`codex/journal-pinning`从`codex/private-images`的`b2eef678a94b65e0f10dab61a634583458a08bba`堆叠交付，未合并前序PR。该起点已修正媒体恢复Compose命令，完整CI通过；证据见 [图片交接](private-images-handoff.md)。07真机输入法仍待人工证据。

## 使用与运行

日记卡片点击“置顶/取消置顶”，主列表跨页优先展示已置顶日记。每组仍按原日记日期、创建时间、ID降序，不按置顶操作时间；不伪造entry_date或created_at。日期详情、搜索、往年今日和回收站仍按原规则排序，只增加置顶标识。

操作期间阻止导航/退出/其他写入；正在编辑同篇时禁卡片动作。成功取消旧分页并刷新首屏，不重挂编辑器，保留正文/标签/图片/冻结创建UUID/冲突状态。409或网络结果不确定要求刷新核对，不猜测反向状态。

已有实例从仓库根目录升级：

```bash
docker compose up -d --build --wait
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic current
```

head为`0006_journal_pinning`：Entry/EntryRevision新增Boolean is_pinned、旧数据false，保留日期索引并增加活跃owner/置顶/日期分页索引。没有新依赖/服务/配置或原图变化，不对有数据实例执行downgrade。

已复用 [18088预览](http://127.0.0.1:18088/)，独立开发库升级0006，仅重启自己的API；未写入预览置顶测试记录、未重置owner/原图。私密启动说明在`/Users/gede/.cache/lifearchive-tags-dev-qockdezn/HANDOFF.md`，0600凭据同目录；18086与其旧库保持原样。

## 接口与实现

- EntryCreate的is_pinned为严格Boolean，省略false；EntryUpdate省略保持、null/字符串/数字拒绝。现有PATCH `{expected_revision,is_pinned}`共用owner/活动记录CAS，递增revision/UTC updated_at并保存全部字段快照；不另建pin接口。
- 创建重放比较revision1的置顶值，后续置顶不使原创建UUID失效。软删除保留状态，恢复后仍置顶；旧历史迁移为false，不根据当前值补造历史。
- `GET /entries?order=date|pinned`默认date，保留旧客户端和日详情语义。日记UI显式pinned，SQL四字段tuple完成跨页排序，与日期/标签过滤AND。
- 日记cursor绑定filter_order及原日期/标签过滤；新增位置is_pinned。缺字段默认date/false兼容旧日期cursor；pinned/date不能混用。置顶变化可移动跨页记录，分页不是快照，写入后刷新首屏。
- 后端入口为journal models/schemas/service/router与0006迁移；前端为`api/journal.ts`、`EntryCard`、`JournalWorkspace`、`PinnedBadge`。其他阅读视图/历史共用标识，不重搭排序框架。
- 导出写 [v4](export-format.md)：当前/修订JSON增is_pinned，其余原图、目录、asset_count、哈希规则不变。CLI只写v4，旧v1–v3仍可独立读取。恢复夹具在原6次修订中覆盖true→false→true，不增加固定日记/图片数量。

## 本轮必要检查

按用户减少测试、先开发功能的要求，没有本机全量回归、构建、浏览器或完整恢复演练；仅执行：

- `tests/journal/test_pinning.py`真实PG4项通过（0.57秒）：完整迁移/ORM一致性、CAS/快照/重放/恢复、全页排序/过滤/旧游标、严格布尔/owner及并发只一次修订。
- 新增置顶导出真实PG1项通过（0.21秒），PortableComparisonTests2项通过（0.002秒），限定Ruff/格式/diff检查通过。
- `npm run typecheck`、`npm run lint`及`src/journal/Pinning.test.tsx`2项通过（791毫秒）；修改文件已格式化。覆盖写锁、取消旧分页、冻结图片草稿/UUID保留、冲突及不确定结果刷新；整合还阻止外部恢复刷新尚未完成时置顶，避免错误后刷新按钮卡住。
- 独立开发库0006迁移成功，18088健康接口正常。前序媒体修正的CI通过仅证明11，不当作本片CI证据。

最小复核（PG配置私密注入TEST_POSTGRES_*）：

```bash
cd apps/server
uv run --locked pytest -q tests/journal/test_pinning.py
cd ../web
npm run typecheck
npm run lint
npm test -- --run src/journal/Pinning.test.tsx
```

## 下一片建议

13建议账户密码修改与会话撤销：当前密码验证、新密码约束、会话轮换/撤销、CSRF与内存草稿保留；先写有界工单，不做公开找回/邮件服务或重置后门。低成本模型接手应复用认证、API client和草稿机制；不重搭服务或删除用户数据。
