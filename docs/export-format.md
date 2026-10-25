# 日记可移植导出格式 v2

`python -m life_archive.cli export-journal` 读取当前唯一 owner 的日记，输出可直接用 ZIP/文本工具阅读的 Markdown、JSON 和完整所选修订。导出不依赖编辑器格式、worker、LLM 或 HTTP 服务。

## 运行

已有 Compose 实例，从仓库根目录执行：

```bash
docker compose exec -T api python -m life_archive.cli export-journal --output /tmp/new-journal-export.zip
```

目标必须为绝对路径、父目录已存在。已有文件、目录或符号链接一律拒绝，不能用 `--force` 覆盖；失败重试请选新路径。ZIP 创建时即为 0600。容器命令运行在已有 API 镜像中，无需停止服务。

默认 `active_only`：当前未软删日记，以及这些日记的全部修订。需要包含软删除的原文、最后修订和完整历史时，显式选择新目标：

```bash
docker compose exec -T api python -m life_archive.cli export-journal --output /tmp/new-journal-export-with-deleted.zip --include-deleted
```

复制到新建的宿主私密目录，然后核验：

```bash
LIFEARCHIVE_EXPORT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/life-archive-export.XXXXXX")"
docker compose cp api:/tmp/new-journal-export.zip "$LIFEARCHIVE_EXPORT_DIR/journal.zip"
chmod 600 "$LIFEARCHIVE_EXPORT_DIR/journal.zip"
export LIFEARCHIVE_EXPORT_FILE="$LIFEARCHIVE_EXPORT_DIR/journal.zip"
```

本机直接运行时，从 `apps/server` 使用 `uv run --locked python -m life_archive.cli export-journal --output /absolute/new-journal.zip`。沿用数据库环境配置，秘密私密注入；先完成迁移和 owner 初始化。没有 owner 或迁移缺失会失败，不自动修复。

## 内容与字段

```text
entries/<entry_uuid>.md
entries/<entry_uuid>.json
revisions/<entry_uuid>/<revision>.md
revisions/<entry_uuid>/<revision>.json
tags.json
manifest.json
```

路径只用固定目录、标准 UUID 和整数修订号；正文、标题、用户名不参与文件名。Markdown 保存 `content_md` 的原始 UTF-8 字节，不加 front matter、不改换行/尾空格/Unicode。JSON 是 UTF-8、键名排序、两空格缩进并以换行结束。

| 文件 | 字段 |
| --- | --- |
| 当前记录 `.json` | `id,user_id,entry_date,occurred_at,occurred_timezone,created_at,updated_at,deleted_at,revision,client_request_id,tags,markdown_path` |
| 修订 `.json` | `id,entry_id,editor_id,revision,entry_date,changed_at,tags,markdown_path` |
| `tags.json` | owner 全部标签的数组，每项 `{id,name,created_at}`，按 UUID 升序 |
| `manifest.json` | `schema_version:2,exported_at,alembic_revision,owner,deleted_policy,entry_count,revision_count,files` |
| `owner` | `id,username,timezone,created_at` |
| `files` 每项 | `path,bytes,sha256`；按 path 升序，覆盖全部 `.md/.json` 数据文件，不递归包含清单自身 |

`deleted_policy` 为 `active_only` 或 `include_deleted`。日期是完整 `YYYY-MM-DD`（年份 0001–9999）；所有 instant 规范为含 `+00:00` 的 UTC ISO 8601，空值保留 null，IANA 时区名保留。历史修订只含当前模型真实保存的字段，不补造历史 occurrence timezone。

`tags` 是按 UUID 升序的 `{id,name}[]`：当前记录从关联读取，修订从不可变快照读取。`tags.json` 包括未使用标签及仅关联软删除日记的标签；`active_only` 仅筛选日记，不筛选 owner 标签目录。目录不导出内部规范化唯一键。旧数据升级后历史标签为空数组。

UUID 升序写当前日记，每篇修订号升序；清单最后写入。ZIP 成员权限为 0600，ZIP 自身的 DOS 时间固定为 1980-01-01，仅用于格式稳定，日记时间始终以 JSON 为准。同一源数据的 Markdown/JSON 文件字节稳定；`exported_at` 每次改变，因此整个 ZIP 的哈希可以不同。

## 一致性和失败语义

导出独占一个数据库连接，在任何源查询前设置 `REPEATABLE READ, READ ONLY`。迁移版本、owner、当前原文、选中成员、标签目录/关联及修订均来自同一快照；开始后并发编辑、标签变更或软删除不会混入半新半旧的数据。

原文与修订用 server-side cursor 分批读取，每批 100 行；只保留当前批正文，清单元数据随文件数增长。导出是一次持续的读取事务，长档案应考虑其执行时长；目前未做大规模性能承诺。

ZIP 关闭、flush/fsync 后，程序通过同一文件描述符重新读取清单及全部文件，逐项校验长度和 SHA-256，再返回成功。不能只凭文件存在或清单存在判断完成。

| 退出码 | 结果 |
| --- | --- |
| 0 | 写入、关闭、完整复核成功；stdout 仅一行 JSON `{output,entries,revisions}` |
| 1 | 输出冲突、目录不可写、数据库/迁移/owner/写入/校验等失败；stdout 无成功信息，stderr 脱敏并给出目标路径 |
| 2 | 参数缺失或未知参数，由 argparse 拒绝 |
| 130 | 收到 KeyboardInterrupt；stdout 无成功信息，stderr 提示保留检查目标 |

失败可能留下空文件、不完整 ZIP，或有清单但尚未验证的 ZIP，均保留 0600、不自动删除。重试不覆盖残留。缺配置、参数错误或排他创建失败时也可能没有创建新文件。

导出含私密原文、修订、标签和 owner 身份元数据。明确排除密码哈希、sessions、token/CSRF、限流、环境、日志、AI 派生物以及尚未实现的媒体。文件未加密。本格式提供独立阅读能力；应用导入、认证恢复、完整数据库与部署恢复另需独立方案，见 [06 恢复演练计划](../tasks/06-restore-rehearsal.md)。

## 独立核验全部文件

下面只读取 ZIP，不解压、不修改文件。可运行在有 Python 3 的独立机器；先将 `LIFEARCHIVE_EXPORT_FILE` 设为实际路径：

```bash
python3 - "$LIFEARCHIVE_EXPORT_FILE" <<'PY'
import hashlib, json, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    names = archive.namelist()
    manifest = json.loads(archive.read('manifest.json'))
    assert manifest['schema_version'] in (1, 2)
    if manifest['schema_version'] == 2:
        assert 'tags.json' in names
    assert len(names) == len(set(names)) and names[-1] == 'manifest.json'
    files = manifest['files']
    paths = [item['path'] for item in files]
    assert paths == sorted(set(paths))
    assert set(names) == set(paths) | {'manifest.json'}
    for item in files:
        digest, size = hashlib.sha256(), 0
        with archive.open(item['path']) as member:
            for chunk in iter(lambda: member.read(65536), b''):
                digest.update(chunk)
                size += len(chunk)
        assert size == item['bytes']
        assert digest.hexdigest() == item['sha256']
    print('PASS:', manifest['entry_count'], 'entries,',
          manifest['revision_count'], 'revisions,', len(files), 'files verified')
PY
```

校验失败时该命令非零退出，不能将该文件作为完整导出使用。格式或字段语义变化应另行升级版本并更新消费者；格式不包含任何执行 SQL/脚本或自动导入步骤。

## 已有 v1 文件

任务 05/06 写出的 v1 文件仍可独立核验：没有 `tags.json`，当前/修订 JSON 没有 `tags` 字段，其余路径、原文、哈希、权限和删除策略约定相同。上面的核验器同时接受 v1/v2；读取者先检查 `schema_version` 再解释字段。当前 CLI 只写 v2，不提供降级写出或 ZIP 导入。历史验收中的文件数和迁移号保留为当时证据，不代表 v2 的数量。
