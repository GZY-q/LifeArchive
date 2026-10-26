# 后续实施与接手计划

当前功能范围为 [16：日记导出界面](../tasks/16-journal-export-ui.md)，按交接继续有界开发和针对性检查。复用v4只读导出与校验，增加鉴权下载、明确限额和Blob生命周期，见 [网页导出交接](journal-export-ui-handoff.md)。[07输入法验收](../tasks/07-editor-compatibility.md)仍待人工证据，无新闻/AI开发。

## 先处理当前交付链

以下是本轮规划时的状态快照；接手时重新查询 PR 和 CI，不用文档代替实时状态。

| 内容 | 当前状态 | 合入依赖 |
| --- | --- | --- |
| M0 基础设施 | 已合入 main | 无 |
| M1 安全日记核心闭环 | PR #2，分支 `codex/m1-secure-journal`，待审阅合入 | main |
| M2 月历/单日原文 | PR #3，分支 `codex/m2-calendar-days`，待审阅合入 | PR #2 |
| M2 归档搜索 | [PR #4](https://github.com/GZY-q/LifeArchive/pull/4)，分支 `codex/m2-archive-search`；[实际验收](m2-search-acceptance.md) | PR #3 |
| M2 往年今日 | [PR #5](https://github.com/GZY-q/LifeArchive/pull/5)，分支 `codex/m2-on-this-day`；[验收](m2-on-this-day-acceptance.md) | PR #4 |
| 只读日记导出 | [PR #6](https://github.com/GZY-q/LifeArchive/pull/6)，分支 `codex/journal-export`；[验收](journal-export-acceptance.md) | PR #5 |
| 隔离恢复演练 | [PR #7](https://github.com/GZY-q/LifeArchive/pull/7)，分支 `codex/restore-rehearsal`；[验收](restore-acceptance.md) | PR #6 |
| 07 输入法验收 | [草稿 PR #8](https://github.com/GZY-q/LifeArchive/pull/8)，`codex/editor-compatibility`，准备/审查已执行，真实矩阵进行中；[接手](editor-validation-handoff.md) | PR #7 |
| 08 日记标签 | [PR #9](https://github.com/GZY-q/LifeArchive/pull/9)，`codex/journal-tags`；[交接](journal-tags-handoff.md)，该提交自动 CI 已通过 | PR #8 的准备文档，代码基线延续 PR #7；不依赖真机矩阵完成 |
| 09 回收站 | [PR #10](https://github.com/GZY-q/LifeArchive/pull/10)，`codex/journal-trash`；[交接](journal-trash-handoff.md)，该提交自动 CI 已通过 | PR #9 |
| 10 归档标签筛选 | [PR #11](https://github.com/GZY-q/LifeArchive/pull/11)，`codex/archive-tag-filter`；[交接](archive-tag-filter-handoff.md)，该提交自动CI已通过 | PR #10 |
| 11 私密图片 | [PR #12](https://github.com/GZY-q/LifeArchive/pull/12)，`codex/private-images`；[交接](private-images-handoff.md)，修正提交b2eef67的全CI及真实媒体恢复已通过 | PR #11 |
| 12 日记置顶 | [PR #13](https://github.com/GZY-q/LifeArchive/pull/13)，`codex/journal-pinning`；[交接](journal-pinning-handoff.md)，该提交自动CI已通过 | PR #12修正提交b2eef67 |
| 13 账户安全 | [PR #14](https://github.com/GZY-q/LifeArchive/pull/14)，`codex/account-security`；[交接](account-security-handoff.md)，该提交自动CI已通过 | PR #13 |
| 14 安全Markdown预览 | [PR #15](https://github.com/GZY-q/LifeArchive/pull/15)，`codex/markdown-preview`；[交接](markdown-preview-handoff.md)，该提交自动CI已通过 | PR #14 |
| 15 标签改名 | [PR #16](https://github.com/GZY-q/LifeArchive/pull/16)，`codex/tag-renaming`；[交接](tag-renaming-handoff.md)，该提交完整自动CI已成功 | PR #15 |
| 16 日记导出界面 | `codex/journal-export-ui`；[交接](journal-export-ui-handoff.md) | PR #16 |

先审阅 PR #2，再审阅 PR #3，再审阅搜索 PR #4、往年今日 PR #5、导出 PR #6、恢复演练 PR #7 和输入法验收 PR #8；每个依赖合入后重新核对后继 PR 的 base、差异和 CI，避免重复提交前一片内容。合并、重写已推送历史和清理旧数据不属于这份计划的自动动作。未经用户明确授权不自行合并。

本轮沿用堆叠PR：16的base为`codex/tag-renaming`，起点`3957c0be510df833ff7c8a90ab4be521b653f0e0`。前序待依赖审阅，不把未合入内容当成main已有。保留用户`.DS_Store`、原文/图片、密码/会话及旧dist，不在预览上替owner执行账户、改名或私密档案下载。

## 建议顺序

| 顺序 / 单 PR 工单 | 可验收结果 | 前置条件 | 明确不包含 |
| --- | --- | --- | --- |
| [04 往年今日](../tasks/04-on-this-day.md)（已交付） | 按选中日期读取以前年度同月同日日记，分页、时区和闰日规则明确 | 依赖搜索 PR #4 的已验收实现，待依次合入 | 新闻、AI、自动回忆推送、修改原文 |
| [05 日记可移植导出](../tasks/05-journal-export.md)（已交付） | 只读 CLI 生成原始 Markdown、JSON 元数据、全部所选日记修订与 SHA-256 清单 | 依赖已验收的 PR #5 和日记/修订模型，待依次合入 | HTTP 下载、队列、媒体、导入、异地备份 |
| [06 独立恢复演练](../tasks/06-restore-rehearsal.md)（已交付） | 在全新 Compose 项目验证 PG dump/restore，并比较原文、修订、owner、日期和迁移 | 依赖已验收的 PR #6，真实 Docker CI 验证 | 覆盖现有库、通用导入器、Restic/远端凭据 |
| [07 真实输入法兼容性](../tasks/07-editor-compatibility.md)（进行中） | 有设备/系统/浏览器/输入法版本和证据的中文输入法、移动软键盘矩阵 | 有可访问的真实设备；06 后作集中验收 | 强制替换编辑器、用模拟事件宣称真机通过 |
| [08 日记标签](../tasks/08-journal-tags.md) | 创建/选择、原子保存和历史、单标签列表过滤、导出 v2 | 现有日记/修订与导出；真机输入法可独立继续 | 标签删除/改名/层级、附件、新闻、AI |
| [09 回收站](../tasks/09-journal-trash.md) | 已删除记录分页、恢复保留原 ID/标签/历史、并发修订检查、草稿保护 | 现有软删除与标签修订；无需迁移 | 永久清除、批量操作、自动清空 |
| [10 归档标签筛选](../tasks/10-archive-tag-filter.md) | 标签单独查找或与关键词/日期AND，已提交条件与分页保持一致 | 现有标签与私密搜索；无需迁移 | 多标签语义、全文/向量索引、标签管理扩展 |
| [11 私密图片](../tasks/11-private-images.md) | 上传原图/鉴权读取、日记关联/历史、v3原图导出、媒体恢复脚本衔接 | 私有本地media卷、新增0005迁移和Pillow13 | 动画/SVG、媒体永久清除、缩略图转码、外部存储/AI |
| [12 日记置顶](../tasks/12-journal-pinning.md) | 主列表置顶优先跨页、严格布尔/CAS/历史、导出v4 | 0006迁移和活跃排序索引，复用日记事务 | 拖拽/自定义顺序、伪造日期、改变其他时间视图排序 |
| [13 账户安全](../tasks/13-account-security.md) | 当前密码验证、改密/撤销旧会话、当前新Session接续、草稿保留 | 复用User/Session/预算，无迁移 | 公开找回/注册、邮件、密码重置后门、设备列表 |
| [14 安全Markdown预览](../tasks/14-markdown-preview.md) | 原文/预览切换、GFM、草稿同textarea、严格URL/HTML/图片策略 | 固定react-markdown10.1.0/remark-gfm4.0.1，无后端变化 | 原始HTML、远程图片、代码执行/高亮、替换编辑器 |
| [15 标签改名](../tasks/15-tag-renaming.md) | 名称校验/冲突保护、管理页、目录刷新、历史快照与ID保持 | 复用08标签唯一约束和历史，无迁移/依赖变化 | 标签删除/合并/层级、重写历史、批量操作 |
| [16 日记导出界面](../tasks/16-journal-export-ui.md) | 显式生成v4 ZIP、活动/回收站范围、全修订/原图/哈希、限额与草稿保护 | 复用只读快照/校验，无迁移/依赖变化 | 导入、队列、任意筛选、自动备份、服务端导出文件 |

05、06 将 M5 中最小的数据可携带、可恢复门槛提前，以便继续积累日记前有可验证的退路。05 的应用导出与 06 的数据库恢复是两个不同交付物：前者供独立读取，后者证明当前数据库可以恢复。计划没有完成或取消 M5；定时备份、加密异地副本、媒体一致性、保留策略和正式环境冷恢复仍属于 M5。

07 的协议和设备预约可提前准备，但未实际执行的矩阵行必须保留“待验证”。没有真机不影响其他独立工作；不能以桌面 Chrome 手机尺寸检查替代 iOS/Android 输入法结论。

## 之后再切片的缺口

- M1：标签/回收站/静态图片/置顶/密码轮换/安全预览/标签改名已分片；更多附件管理仍可后续切片。07真机矩阵未完，不能宣布全部M1验收完成。
- M2：10补齐单标签归档条件；月历、单日原文、搜索、往年今日已有独立交接。大规模数据索引与性能需另行测量，不把字面子串查询称为已完成中文全文检索。
- M3/M4：保留 [原 roadmap](roadmap.md) 中新闻摄取、任务台账、来源校验、AI 摘要的先后关系。未另行分配之前不启动，不预建未来表或服务。
- M5：11修正提交的Docker媒体恢复/负例已由CI验收，本机未追加完整演练。正式部署、自动加密异地备份、保留策略与生产冷恢复仍需后续，不能将合成演练称为生产备份上线。

16后建议17做“导出范围预检”：显式读取所选篇数/修订数和原图体积，让用户在生成前判断是否适合网页下载；说明预检与生成是不同快照，最终限额仍由生成事务验证。先定义契约再补工单，不做队列/导入或覆盖已有库。标签/媒体永久清除仍另切片，须定义历史/备份保留。当前只规划，不提前开发新闻/AI。

## 每片的完成门槛

1. 阅读 `AGENTS.md`、README、产品/架构/数据模型、相关交接和本片工单；报告当前分支、依赖、工作区改动以及精简实现计划。
2. 复用现有模块、认证、日期语义、API client、迁移链和测试夹具。按工单实现，不升级无关依赖、不重搭框架。
3. 新行为有针对性测试。需要 PostgreSQL 的测试必须连接专用真实 PG；跳过、未运行、失败分别记录，不能统称通过。
4. 只读功能证明没有日记/修订写入。原始 Markdown、`entry_date`、UTC instant、owner 隔离、软删除与草稿/创建幂等约定保持成立。
5. 更新接口或 CLI 文档、验收记录与接手说明，提供精确运行命令；列出配置/迁移影响、未解决限制和下一片入口。
6. 提交可审阅的单个 PR，说明变化、测试、运行方式、迁移影响、风险和剩余项。合并需沿用用户授权，不能因 CI 通过就自行合并。

遇到接口契约需要扩张、必须引入新服务/依赖/迁移、真实数据不可逆操作、恢复目标已经存在，或无法验证关键验收项时，先停止对应步骤，保留现场并写明原因。可以继续不依赖该阻碍的文档或测试；不能自动删库、覆盖文件、伪造通过或改做下一里程碑。

## 可直接交给接手模型的提示词

将下面的 `NN` 替换成这次明确分配的工单编号，一次只选一张：

> 先读 AGENTS.md、README.md、docs/product.md、docs/architecture.md、docs/data-model.md、docs/security-and-backup.md、docs/next-steps.md、已有交接与 tasks/NN 的完整工单。检查工作区、当前分支、上游 PR 和 CI；保留用户改动。先给简短实施计划，再仅实现这一片。复用已有 auth/journal/timeline、数据库事务约定、日期工具和 API client，不重搭基础设施，不顺手开发未来功能。严格遵守该工单的 API/CLI、排除项和验收。新增行为有测试，真实 PostgreSQL 验证不能用 skip 代替；原文、修订、用户日期、UTC 时间、权限、草稿和创建幂等不得回归。交付代码、测试、文档、精确命令、验收证据和单个 PR，说明迁移影响与未完成项。需要删除、覆盖现有数据或其他不可逆操作时，先展示具体对象和方案等待确认；未获授权不合并 PR。只规划下一张，不自动实施。
