# Task 数据可携带门槛 — 只读日记导出（待分配）

状态：仅规划，未实施；一个 PR。依赖 04 和当前安全日记/修订模型已验收合入。本片提前验证 M5 的最小可移植导出，不代表备份系统或恢复功能已完成。

## 固定 CLI

扩展现有 `python -m life_archive.cli`，新增：

```bash
python -m life_archive.cli export-journal --output /absolute/new-journal-export.zip
python -m life_archive.cli export-journal --output /absolute/new-journal-export-with-deleted.zip --include-deleted
```

- 只允许本地管理 CLI，沿用当前数据库环境配置；不添加 HTTP API、worker、定时任务或 owner 参数。读取数据库唯一 owner，没有 owner 或迁移缺失时明确失败，不初始化/修复数据库。
- `--output` 必填绝对路径，父目录须存在。使用排他创建并拒绝已存在的普通文件、目录和符号链接，禁止 `--force` 或自动覆盖。成功文件权限为 0600；先限制权限再写入。
- 默认仅导出未删除日记，以及这些日记的**全部修订**。`--include-deleted` 另外包含软删除日记及全部修订，保留 `deleted_at` 和最后修订。清单明确记录策略；不能默默漏掉所选日记的旧版本，也不复活日记。
- 导出是只读操作，开始任何查询之前创建独立的 PostgreSQL `REPEATABLE READ, READ ONLY` 事务；owner、当前原文、修订和迁移版本在同一一致性快照读取。不要在已有认证/查询事务中事后切换隔离级别。
- 分批读取/写入 ZIP，避免一次加载全部 Markdown。成功时最后写 `manifest.json`，关闭 ZIP 后才返回 0。失败返回非零、不给“完成”提示；可能留下没有完整清单的私密残留文件，保留并报告路径，不自动删除或覆盖重试。清单及全部哈希校验通过才算完整导出。
- 标准输出仅包含路径和记录数量；错误信息不包含连接串、密码、会话数据或日记原文。保持已有 `init-owner` 行为不变。

## 格式 v1

UTF-8 ZIP，路径仅由程序常量、标准 UUID、整数修订号生成，禁止由日记标题/正文/用户名拼接路径：

```text
manifest.json
entries/<entry_uuid>.md
entries/<entry_uuid>.json
revisions/<entry_uuid>/<revision>.md
revisions/<entry_uuid>/<revision>.json
```

- `.md` 是数据库 `content_md` 的原始 UTF-8 字节，不加 front matter，不规范化换行、尾空格或 Unicode，不渲染 HTML。
- 当前记录 JSON 保留 `id`、`user_id`、`entry_date`、`occurred_at`、`occurred_timezone`、`created_at`、`updated_at`、`deleted_at`、`revision`、`client_request_id` 和对应 Markdown 路径。
- 修订 JSON 保留 `id`、`entry_id`、`editor_id`、`revision`、`entry_date`、`changed_at` 和对应 Markdown 路径。不要凭当前模型虚构历史上没有保存的 occurred timezone 等字段。
- 所有 instant 输出带 UTC 时区的 ISO 8601；日期保持 `YYYY-MM-DD`，空值保持 null，时区名保持原值。UUID/修订顺序明确，JSON 序列化稳定，便于跨导出比较数据文件。
- `manifest.json` 包含 `schema_version:1`、UTC `exported_at`、源 Alembic revision、owner 的 `id/username/timezone/created_at`、软删除策略、entry/revision 数量，以及按路径排序的文件表 `{path,bytes,sha256}`。文件表覆盖每个数据文件，不对清单自身递归计算哈希。
- 导出明确排除 `password_hash`、sessions、token/CSRF、登录限流数据、环境配置、日志、AI 派生物及未实现的媒体/标签。owner 标识和用户名属于归属元数据，不能误认为导出已匿名化。

## 实现入口

新增小模块 `apps/server/src/life_archive/journal/export.py`，管理快照读取与格式；`cli.py` 只负责参数/命令分发。复用 `db.py` engine、`auth.models.User` 和 `journal.models`。增加 `apps/server/tests/journal/test_export.py` 及 CLI 回归；更新 README，新增 `docs/export-format.md` 和真实验收/交接说明。无表、迁移、依赖或锁文件变化；Python 标准库提供 ZIP、JSON 和 SHA-256。

## 验收与运行

真实 PG 测试覆盖原始中文/emoji/换行/尾空格、补记日期、UTC instant/时区/空值、多个修订、默认排除软删除与显式包含、空档案、owner 归属、全文件 SHA-256、明确排除敏感字段。使用两个连接，在导出已建立快照后并发编辑/软删除，证明当前记录和修订仍来自同一快照；导出前后源日记、修订和认证表没有写入。

覆盖已存在文件/目录/符号链接不被修改、不可写目录/中断失败非零、残留不得被称为成功、`init-owner` 回归。打开 ZIP 逐项核验清单，不能仅断言文件存在。

未来实现后，已有隔离 Compose 实例的运行示例为：

```bash
docker compose exec -T api python -m life_archive.cli export-journal --output /tmp/life-archive-export.zip
LIFEARCHIVE_EXPORT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/life-archive-export.XXXXXX")"
docker compose cp api:/tmp/life-archive-export.zip "$LIFEARCHIVE_EXPORT_DIR/archive.zip"
```

容器内目标若已存在，第一步必须拒绝；选择另一个新路径后再运行，不能用删除或覆盖绕过。宿主目标目录由 `mktemp` 新建，导出不进 Git。交付文档需提供逐文件 SHA-256 复核命令及准确退出码语义。

从 `apps/server` 运行 `uv run --locked pytest`、`uv run --locked ruff check . ../../scripts ../../tests`、`uv run --locked ruff format --check . ../../scripts ../../tests`，配置专用真实 PG，不以 skip 充当验收。PR 附一次合成样本导出及哈希核验结果，不提交私密 ZIP/数据库。

排除：应用导入、数据库恢复、HTTP 下载、媒体导出、导出加密、自动备份、远端上传、压缩格式选择器和大规模迁移工具。README 必须说明本格式供独立读取，不等于可恢复认证/整个部署的数据库备份。
