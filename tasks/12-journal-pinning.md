# 12 — 日记置顶

用户继续功能开发，推进11交接规划的置顶；用子代理分工，少量关键检查，不做本机全量/浏览器/恢复演练。从`codex/private-images`修正媒体恢复命令后的`b2eef678a94b65e0f10dab61a634583458a08bba`堆叠交付，不自动合并。保留用户`.DS_Store`、预览数据/原图、18086输入法环境，07真机矩阵仍待证据。

## 固定契约

- 新增`0006_journal_pinning`：Entry与EntryRevision各增非空Boolean `is_pinned`，旧记录/旧历史默认false。新建owner/active置顶排序索引 `(user_id,is_pinned DESC,entry_date DESC,created_at DESC,id DESC)`，原日期索引保留。
- EntryCreate增加严格Boolean is_pinned，默认false；EntryUpdate增加可选严格Boolean is_pinned，省略保持、null拒绝。至少一个editable字段；只改置顶也按expected_revision执行现有CAS，递增revision/UTC updated_at，和标签/附件同事务快照。不改原文、entry_date、created_at。
- 创建UUID重放比较revision1的is_pinned（省略等价false），后续置顶不使原始创建请求失效；不同首次pin值返回既有idempotency_conflict。软删除保留置顶状态，恢复后仍置顶；历史保留各次bool，不反推旧快照。
- EntryResponse、RevisionResponse（包括所有读取视图和回收站）新增is_pinned。
- `GET /entries`新增`order=date|pinned`，默认date，保持旧API/日详情语义。pinned按`(is_pinned DESC,entry_date DESC,created_at DESC,id DESC)`，每组仍按日记日期；无“最新置顶时间”语义。与日期/tag AND过滤可组合。
- EntryCursor新增filter_order默认date和位置is_pinned默认false，校验order与原日期/标签条件。date模式兼容旧无新字段游标，pinned/date不能混用。日期模式仍3字段tuple，pinned模式4字段tuple，不能只在前端当前页重排。分页不是跨请求快照，置顶变更会移动条目，需刷新。
- 日历/单日、搜索、往年今日、回收站排序继续原语义，不以置顶改变时间归档；只有日记主列表显式order=pinned。没有新服务/依赖/专用pin endpoint。

## 前端

EntryCard提供“置顶/取消置顶”与状态标识，PATCH只发expected_revision+is_pinned。列表显式order=pinned，变更后取消旧分页、刷新首屏，前后页均遵循后端排序；不要修改日期伪造位置。

置顶写入用既有全局onBusy，期间阻止导航/退出/其他写入；正在编辑同篇时禁卡片动作，不重挂编辑器，不覆盖草稿/图片/冻结创建UUID/409面板。成功后提示，409提示刷新核对，网络不确定不显示成功或盲目反向切换。历史与其他阅读视图显示置顶标识；没有拖拽、排序框架或置顶上限设置。

## 导出与恢复

当前/修订JSON加入is_pinned，写出schema_version4；其余v3媒体/清单约定不变，保留v1/v2/v3独立读取说明，当前CLI只写v4。同步导出/恢复脚本和必要夹具：合成现有修订内覆盖置顶/取消、不增加固定修订数，核对当前与历史布尔值；DB恢复自然包含新列。

## 交付

代码、少量关键测试、迁移/接口/导出/交接/准确运行命令和独立PR。只升级18088独立开发库并重启自己的API，不写预览置顶测试记录，不重置owner或图片；不动18086。媒体CI修正单独在前序PR记录，未通过不写成成功。下一片只规划。
