# 11 私密图片附件交接

范围见 [11工单](../tasks/11-private-images.md)。分支`codex/private-images`从`codex/archive-tag-filter`的`5bc0e98179191476fa70f9888c9fb8903a9f6a6f`堆叠交付，前序PR按依赖审阅，不自动合并。07真机输入法仍待人工证据，不以本片自动化替代。

## 使用与运行

编辑日记时选择单张原图上传，完成后加入草稿，保存日记时原子关联，最多10图且正文仍必填。支持静态JPEG/PNG/WebP，单图5MiB、2000万像素、单边20000；不支持动画/SVG。图库默认折叠，展开才鉴权读取，提供原图下载。原字节/EXIF保留，不转码或发送外部服务。

上传期间禁止保存、导航和退出；已完成的图片选择随正文/标签草稿保留，创建请求冻结asset_ids，冲突基于新revision继续时保留本地选择。上传结果不确定可重选同一文件，服务器按owner+SHA-256幂等去重。移除只解除当前草稿关联，原文件仍保留；取消草稿或软删除不清除历史图片。

已有实例从仓库根目录升级：

```bash
docker compose up -d --build --wait
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic current
```

head为`0005_private_images`：新增assets/entry_assets及revision.assets JSONB，旧历史默认[]，不改原文；仅新增Pillow13.0.0锁定依赖。Compose新增`media`卷，API读写、worker只读、web不挂载；镜像预建0700目录归UID10001，不用临时提权修权限。不要对有数据实例downgrade或删除卷。

本机API开发须额外设置：

```bash
export LIFEARCHIVE_MEDIA_ROOT=/absolute/private-directory
export LIFEARCHIVE_MEDIA_QUOTA_BYTES=1073741824
```

目录为私密绝对路径，默认容器内`/var/lib/lifearchive/media`。配额统计owner全部已登记原文件，包括未关联和历史/回收站，默认1GiB；固定单图和像素上限不可被请求放宽。没有资产删除/GC或自动清空配额。数据库失败后可能有未登记孤立文件，保留现场，不自动覆盖或删除。

本机 [18088预览](http://127.0.0.1:18088/)已沿用独立开发库/owner升级0005；原文件位于`/Users/gede/.cache/lifearchive-tags-dev-qockdezn/media`，0700。私密启动说明与0600凭据在其父目录HANDOFF.md/credentials.json，不提交密码。18086及其输入法库保持原样。本轮未向预览上传或删除测试图片。

## 实现与权限边界

- `media/models.py`、`schemas.py`：不可变资产、owner复合FK与公开元数据。`settings.py`管理根目录/配额；`media/service.py`验证格式、尺寸、完整解码，按owner行锁串行去重/配额检查。
- `media/storage.py`：UUIDhex存储键、目录FD/O_NOFOLLOW、独占0600写入与fsync，读取核对普通文件/大小/SHA-256；不接收用户路径/文件名。失败保留新文件，不覆写已有原图。实现依据：[Pillow verify/load与像素限制](https://pillow.readthedocs.io/en/stable/reference/Image.html)。
- `POST /assets`原二进制body、正确Content-Type、Origin/CSRF/X-LifeArchive-Request；流式计数，图片验证和DB/文件操作在线程池。`GET /assets/{id}`只允许owner，包括草稿/历史/回收站图片；401/404/503脱敏，无匿名静态路径。所有响应no-store，原图nosniff及安全生成inline文件名。
- `journal/service.py`：asset_ids与正文/日期/标签共用CAS事务，最多10个不同owner资产；当前/历史资产按UUID排序。附件单独变更也增加revision，创建重放按revision1资产ID集合比较。删除/恢复仍保留原文件与所有历史。
- `api/assets.ts`、`journal/AssetPicker.tsx`、`AssetGallery.tsx`：同源鉴权Blob，展开才读取，收起/卸载取消并回收object URL；401移除私密DOM。各日记视图复用图库，没有Blob/File持久化。移动端真实图片操作尚未手测。

## 导出和恢复

[格式v3](export-format.md)增加当前/修订assets、assets.json、原图及asset_count。只包含所选日记当前或全部历史引用union；默认不含仅被未选软删除日记引用的图片，未关联上传始终不含。原图缺失/损坏时失败，不输出成功。v1/v2仍可独立读取/核验，CLI只写v3。

完整备份必须同时保留数据库和media卷，只有PG dump不包含原图。恢复脚本已补2张合成PNG、元数据/关联/历史/原文件哈希；DB恢复后初始化自有空media卷，验证volume/容器归属，以受限base64 JSON和一次性helper独占写入，再启动目标API。不解压任意tar，不接受已有媒体目录覆盖。

## 必要验证与限制

按用户减少测试、功能优先的要求，仅执行：

- 真实PG `tests/journal/test_assets.py`：5项通过（3.11秒），含原字节/权限/owner、流式与格式边界、并发去重/配额、CAS/重放/历史、损坏/缺失/符号链接；首项同时确认迁移与ORM元数据一致。
- 新增原图导出2项真实PG通过（0.32秒）；恢复标准库16项通过（0.012秒），不能替代真实Docker恢复。
- 前端typecheck/lint、`src/journal/Assets.test.tsx`3项通过（570毫秒），含上传CSRF/写锁、跨视图/401/冻结创建草稿、按需鉴权Blob/回收和人工去重重试；修改文件已格式化。
- 限定后端/脚本Ruff检查、Compose静态配置和diff检查通过；独立开发库0005迁移成功。

没有运行本机全量回归、生产镜像构建、浏览器演练、完整Docker媒体恢复或真机矩阵。CI由PR自动触发，旧CI不作为本片证据；不能将更新后的脚本称为媒体恢复已验收。

后续检查发现首轮[自动CI 40251708989](https://github.com/GZY-q/LifeArchive/actions/runs/40251708989)的backend/frontend/compose通过，restore在创建目标媒体容器时失败：Compose `create`不支持`--no-deps`。已按本机Compose帮助修正为`--no-recreate --pull never`，创建停止态API和卷，同时保留已恢复PG；不再对create传不支持的选项。修正后的Docker恢复结果需以后续CI为准，不将初次失败记录为通过。

修正提交`b2eef678a94b65e0f10dab61a634583458a08bba`的[CI 40266974089](https://github.com/GZY-q/LifeArchive/actions/runs/40266974089)已全部成功，含真实Docker数据库+原图恢复、鉴权读取/导出比较及损坏备份拒绝。此为11的合成数据验收，本机未追加完整演练，也不代表生产备份上线或后续置顶提交已验收。

最小复核（PG配置私密注入TEST_POSTGRES_*）：

```bash
cd apps/server
uv run --locked pytest -q tests/journal/test_assets.py
cd ../web
npm run typecheck
npm run lint
npm test -- --run src/journal/Assets.test.tsx
```

## 下一片

建议12做日记置顶，先明确排序/分页、revision冲突、导出和历史语义，不伪造日期或创建时间。未关联上传管理与永久清除另切片，先定义历史/备份保留，不在本片顺手删除文件。低成本模型接手应复用media、CAS、图库和导出接口，不重搭服务。
