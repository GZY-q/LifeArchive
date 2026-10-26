# 10 归档标签筛选交接

范围见 [工单](../tasks/10-archive-tag-filter.md)。分支 `codex/archive-tag-filter` 从 `codex/journal-trash` 的 `7e5a4ff88e1f06c44d9da884bb2d8b3104ef5e21` 开始；依赖前序堆叠PR，不自行合并。07真机输入法矩阵仍待人工证据，本片没有以自动化替代。

## 使用与运行

登录后进入“归档”，选择标签并点击“搜索日记”；也能与关键词、起止日期组合，所有条件须同时满足。只选择标签也是有效查询。选择“不限标签”时保留原搜索语义，完全空条件仍拒绝。

标签目录从既有分页接口读取，失败可单独重试；不阻塞原文/日期查询。修改表单不自动搜索，结果摘要、分页与失败重试始终对应上次已提交条件。离开归档取消请求、卸载结果，回到归档保留同页标签表单，重新搜索才读取；退出登录清空。日记草稿继续由现有认证边界保留。

已有标签/回收站版本从仓库根目录运行：

```bash
docker compose up -d --build --wait
docker compose exec -T api alembic current
```

无迁移、配置或依赖变化，head仍`0004_entry_tags`，导出仍v2。更早版本按根README显式迁移，不重置owner或数据。沿用 [18088开发预览](http://127.0.0.1:18088/) 和原开发库；私密启动说明在 `/Users/gede/.cache/lifearchive-tags-dev-qockdezn/HANDOFF.md`，凭据同目录 `credentials.json`（0600）。18086输入法环境保持不动。

## 实现入口与约定

- `search/schemas.py`：SearchRequest增加可选UUID `tag_id`，默认null；标签可作为唯一非空条件。无效输入通用422，不回显关键词或标签。
- `search/service.py`：owner EntryTag EXISTS 与关键词/日期 AND；只读活动记录，未知或其他owner标签返回空结果。当前标签变化/软删除/恢复在重新搜索后生效，历史修订标签不参与匹配。
- `search-v1`摘要只在非空标签时加入规范UUID，省略/null继续旧算法。分页不能跨标签、日期、关键词、owner或接口复用。无新索引或大规模性能承诺。
- `api/search.ts`、`search/form.ts`、`ArchiveWorkspace.tsx`：标签表单、独立目录读取/重试、提交标签名称快照、请求取消与条件保持。不使用URL或浏览器持久存储保存搜索条件。
- 无标签请求可以省略tag_id，保持既有客户端调用与游标兼容。所有条件和cursor仅在原POST体；认证、Origin/CSRF、no-store和原文纯文本显示沿用既有机制。

## 必要检查

按用户要求以功能开发为主，不运行本机全量回归、浏览器演练、完整恢复或真机输入法矩阵。

后端真实PostgreSQL仅执行 `tests/search/test_tags.py`：**3项通过**（0.65秒）。覆盖标签单独/组合查询、当前关联及软删除/恢复、只读、标签游标隔离和旧摘要兼容、未知/越权及无效输入。限定Ruff和diff检查通过。

前端 `npm run typecheck`、`npm run lint` 通过；`npm test -- --run src/search/ArchiveTags.test.tsx` **2项通过**（690毫秒），覆盖目录分页、标签单独查询、已提交摘要/分页/重试稳定、跨视图表单/正文草稿保留，以及目录失败不阻塞其他搜索、独立重试不触发搜索。修改文件已格式化。

仅重启自己的开发API加载本片代码，不迁移或写入预览数据。18088健康接口正常。CI由PR自动触发，未用前一片结果替代本片验收。

后续只读查询确认：提交 `5bc0e98179191476fa70f9888c9fb8903a9f6a6f` 的 [自动CI 40249901153](https://github.com/GZY-q/LifeArchive/actions/runs/40249901153) 已成功；本机未追加全量运行。此结果只属于10，不代表图片功能。

最小复核命令（PG配置安全注入 `TEST_POSTGRES_*`，skip不等于通过）：

```bash
cd apps/server
uv run --locked pytest -q tests/search/test_tags.py
cd ../web
npm run typecheck
npm run lint
npm test -- --run src/search/ArchiveTags.test.tsx
```

## 下一片建议

11建议私密图片附件：先确定上传大小/MIME边界、原文件存储、鉴权读取、日记关联，以及导出/恢复一致性，写出有界工单后再实施。沿用私有本地存储，不增加对象存储、OCR或图片AI。低成本模型接手应复用已有owner隔离、原子保存、修订与导出机制，不另搭基础框架。
