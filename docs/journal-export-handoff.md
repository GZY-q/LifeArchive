# 只读日记导出交接

范围见 [05 工单](../tasks/05-journal-export.md)、[格式与运行命令](export-format.md)、[验收证据](journal-export-acceptance.md)。本片 [PR #6](https://github.com/GZY-q/LifeArchive/pull/6) 从 PR #5 的 `97b53106265a4ddf02885c3437a6def773ef44a5` 新建 `codex/journal-export`，前序 #2–#5 仍待合入，依次审阅并复核后继 PR 的 base/差异/CI，不自动合并。

## 实现入口

- `apps/server/src/life_archive/journal/export.py`：独立只读快照、Core 流式读取、固定文件格式、排他私密文件、写后完整验证；导出服务接受 Engine 和绝对 Path，不借用已有认证 Session。
- `apps/server/src/life_archive/cli.py`：`export-journal` 参数分发和统一脱敏错误/退出码。既有 `init-owner` 密码输入及拒绝覆盖 owner 的行为保留。
- `apps/server/tests/journal/test_export.py`：真实 PostgreSQL 的格式、并发快照、只读源数据、批量、软删除、文件权限/覆盖/异常和 CLI 回归。
- `scripts/smoke-export.py`：在隔离 API 容器内运行实际 CLI，并独立验证哈希、权限、删除策略和源数据不变；接在已有 HTTP/Chrome 合成夹具后，覆盖已打包镜像。

## 必须保持的约定

输出 `O_CREAT|O_EXCL`，0600 在任何数据写入前生效；拒绝已有文件、目录及符号链接。没有 force、覆盖或自动清理。失败可保留残留，CLI stderr 只打印固定脱敏原因和转义的目标路径；禁止把数据库异常 repr、环境或原文打印出来。

所有源查询前配置 `REPEATABLE READ` 和 PostgreSQL readonly，之后同一事务中读迁移版本、owner、entries、entry_revisions。通过 owner ID 限制当前记录，仅对选中成员读取全部修订。默认排除软删，include-deleted 明确包含；不修改原文、修订、认证或限流状态。

元数据采用显式字段白名单。原始 Markdown UTF-8 字节不变；时间转 UTC、日记日期不变。成员路径由固定常量/UUID/修订号生成。清单最后写，ZIP 关闭后逐文件复核，验证后才返回 0。保留 TypedDict/ExportResult，未来字段变化应更新格式版本和独立核验示例。

当前每篇日记一个修订流查询，批大小 100；正文不会全部驻留内存，但清单占用随文件数量增长。大档案的长快照与性能仍需测量，不能把此片称为完整备份上线。

## 精确运行与检查

已有实例重建后按 [格式文档](export-format.md#运行) 运行 CLI。应用数据表/迁移、依赖和环境配置没有变化，head 仍为 `0003_journal`。CLI 可独立于正在服务的 API 执行；生成 ZIP 后复制到新的私密位置并核验。

从 `apps/server` 执行；先私密设置专用 `TEST_POSTGRES_{HOST,PORT,USER,PASSWORD,DB}`，不能用 skip 代替真实 PG：

```bash
uv run --locked pytest
uv run --locked ruff check . ../../scripts ../../tests
uv run --locked ruff format --check . ../../scripts ../../tests
```

专项命令：`uv run --locked pytest tests/journal/test_export.py tests/auth/test_owner_cli.py`。根目录执行 `python3 -m unittest discover -s tests -v`；前端沿用 lint、format:check、typecheck、test、build。CI 自动运行全套和容器内导出。

仅在按 [M1 隔离验收流程](m1-handoff.md#精确运行与测试) 启动的测试实例中，完成 HTTP/Chrome 夹具后复跑容器导出：

```bash
docker compose exec -T --env LIFEARCHIVE_EXPORT_SMOKE_PROJECT="$COMPOSE_PROJECT_NAME" \
  api python - --allow-isolated-export < scripts/smoke-export.py
```

临时测试项目需以 `life-archive-ci-` / `life-archive-smoke` 开头；该环境变量只是验收脚本的隔离确认，不是新增应用配置。脚本保留自己的私密临时 ZIP，不写源数据库，也不清理卷。

下一片建议 [06 独立恢复演练](../tasks/06-restore-rehearsal.md)，本轮未实施；正式加密异地备份、媒体一致性和冷恢复仍属于 M5。任务 07 真实输入法、M1 标签/附件等缺口见 [下一步](next-steps.md)。
