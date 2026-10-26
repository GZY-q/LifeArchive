# 11 — 私密图片附件

## 范围

继续功能开发：原图上传、日记关联、登录后读取/下载、修订快照、原文件导出及隔离恢复脚本衔接。子代理分工实现，减少测试，仅必要静态与关键用例；不做完整本机回归/浏览器/恢复演练。从 `codex/archive-tag-filter` 的 `5bc0e98179191476fa70f9888c9fb8903a9f6a6f` 堆叠交付，不自行合并。保留用户数据、`.DS_Store`和18086输入法环境。

## 存储与上传

- 新增media模块，Pillow固定13.0.0验证图片内容，拒绝无效/截断/动画/SVG/HTML；只收静态JPEG/PNG/WebP，单文件最多5MiB、最多20,000,000像素，任何边最多20,000。验证后保留原始字节/EXIF，不转码、不发外部服务。新依赖只加Pillow，不引入multipart服务或对象存储。
- `POST /api/v1/assets`：原始二进制body，Content-Type必须与检测格式一致；会话、可信Origin、X-LifeArchive-Request与CSRF必需。流式计数限制body（Content-Length不可信），超限413、格式不符422。读完后在线程池执行同步图片/DB/文件操作，不能在事件循环做阻塞查询。
- AssetResponse固定 `{id,mime_type,byte_size,sha256,width,height,created_at}`。同owner相同sha256幂等返回已有200，新上传201；按owner行锁串行核对配额，默认总已登记原文件1GiB，超限413。无文件名输入，名称不进入路径。相同内容只登记一次；新文件独占创建0600、fsync后再提交元数据，失败不删除已有文件，可能的孤立文件保留后续人工处理，不自动GC。
- `GET /api/v1/assets/{id}`：只允许资产owner，未认证401、未知/越权404；原始字节，正确MIME、no-store、nosniff、安全生成的inline文件名。允许owner读取未关联或仅关联回收站/历史的上传，以支持草稿与恢复。私有目录不挂到Caddy，不暴露匿名URL。
- MediaSettings：`LIFEARCHIVE_MEDIA_ROOT`默认`/var/lib/lifearchive/media`；`LIFEARCHIVE_MEDIA_QUOTA_BYTES`默认1073741824。固定单文件/像素上限不由请求放宽。存储key为资产UUID的32位hex，无目录或客户端路径；拒绝符号链接/非普通文件，读取检查字节数/sha256，损坏/缺失通用503，不返回服务器路径。
- `media/storage.py`提供 `read_original(asset: Asset | Mapping[str, object], root: Path | None = None) -> bytes`，供API与导出/恢复共用；字段需storage_key、byte_size、sha256，失败抛脱敏MediaStorageError。
- Compose新建私有media卷，仅API读写、worker只读；镜像预建目录并赋10001权限。本机开发指定工作区外私密目录。

## 模型、日记和修订

- 新增`0005_private_images`：`assets(id,user_id,mime_type,byte_size,sha256,width,height,storage_key,created_at)`，唯一(owner,sha256)、(id,user_id)；`entry_assets(entry_id,asset_id,user_id)`双owner复合FK。类Asset/EntryAsset放media/models.py，仅引用外键字符串，避免循环导入。
- Entry.assets为viewonly/selectin关系，按UUID排序；EntryRevision新增assets JSONB，旧历史默认[]。AssetResponse字段快照（UUID/时间字符串），immutable且不含storage_key/user_id。
- POST/PATCH日记增加asset_ids：至多10个不同UUID，创建省略[]，PATCH省略保持、[]解除当前关联、null拒绝；无权/不存在统一422。先成功revision CAS，再替换关联、快照、一起提交；附件单独变更也增加修订。创建UUID重放对比revision1资产ID集合，顺序不影响。删除/恢复快照保留当时附件，原文件及旧关联引用不自动清理。
- EntryResponse/RevisionResponse/TrashEntryResponse增加assets（上面的完整公开元数据数组，按UUID）。Markdown仍原样，不自动插入图片语法，不允许只有图片的空正文。

## 前端

编辑区单文件选择并上传，完成后加入草稿，最多10图；保存日记时原子提交asset_ids。移除仅解除草稿关联，明确原文件仍保留。上传期间用既有onBusy阻止导航/退出/保存，不确定结果可重选同一文件幂等重试，不自动重复上传；失败保留原草稿和已上传选择，401同页重新登录保留已完成的附件草稿。

用通用AssetGallery/AssetPicker复用组件；原图由同源鉴权fetch获取Blob，no-store，object URL仅内存，卸载/会话失效撤销，401触发既有expire；可手动下载原图。当前日记/历史/日历/往年今日/搜索/回收站均显示关联图片；懒加载、可重试，不显示服务器路径。草稿附件、冻结创建请求、409比对和跨视图状态规则沿用现有机制，不把Blob或File写入浏览器持久存储。

## 导出与恢复

- 导出写出v3；当前/修订JSON增assets，新增assets.json与assets/<UUID>.<jpg|png|webp>原字节，全部纳入哈希清单，manifest增加asset_count。只导出所选日记当前或历史引用的资产；未关联上传和仅被未选软删除记录引用的资产不在默认导出，需数据库+media卷备份保留。
- DB元数据同一只读RR快照，图片上传后不覆写，导出逐文件校验已登记大小/哈希；文件缺失或损坏失败，不输出成功。保留v1/v2阅读/核验说明，当前CLI只写v3，无ZIP导入。
- 同步smoke-export、restore fixture/snapshot/checks及恢复脚本：合成图片、Asset/EntryAsset/修订/原文件哈希，隔离源media复制到自有空目标media后才启动目标API；不覆盖已有目标、不解压任意用户tar、不删除源或卷。根unittest格式夹具同步；不在本轮运行完整Docker恢复。

## 交付

功能+少量关键测试+API/存储/迁移/导出/运行/交接文档与独立PR。不要把仅PG dump称为含媒体完整备份。迁移只升级18088独立开发库，配置新私密目录；不动18086旧库，不重置owner。下一片只规划。
