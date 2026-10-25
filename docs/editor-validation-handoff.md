# 输入法验收准备与接手

范围见 [07 工单](../tasks/07-editor-compatibility.md)，具体用例和真实矩阵见 [验收协议](editor-compatibility.md)。本片 [草稿 PR #8](https://github.com/GZY-q/LifeArchive/pull/8) 基于恢复 PR #7 的 `c13c29398b5052e23e0b83f46d302a2da0c13614`，分支 `codex/editor-compatibility`，前序依赖尚未合入。

**当前仅完成审查、协议和隔离环境准备，真实矩阵尚未完成。** 用户表示可配合 macOS/Windows 桌面操作；未收到并核实的步骤保持待验证。软件版本盘点、Vitest、CDP 或手机尺寸不是候选窗口/移动软键盘的通过证据。

## 子智能体交付

- `ime_audit`：只读审查 MarkdownEditor、EntryForm、AuthGate 和相关回归，未发现可确认缺陷；无实现改动。
- `ime_protocol`：六行设备矩阵、C01–C06 手工步骤、合成样本、409/401/未确认创建的复现入口和证据模板；无实现改动。
- 主代理：复核报告/协议，准备独立合成测试库及 loopback API/Web，收集实际桌面结果并核对源数据；不将协议或模拟事件称为 task07 完成。

## 已执行自动化

2026-10-26，从 `apps/web` 执行：

```bash
npm test -- --run src/journal/JournalWorkspace.test.tsx src/auth/AuthGate.test.tsx src/calendar/CalendarWorkspace.test.tsx src/search/ArchiveWorkspace.test.tsx
```

结果：**4 文件、37/37 通过**，Vitest 5.0.5。审查时没有修改实现，沿用现有受控原文适配层和草稿/UUID/409/401 约定。

另一次 Chrome/CDP 自动化使用现有 dist、临时 loopback 静态服务和 mocked API：composition 后真实鼠标事件切到日历再回日记，原文保留，事件为 `compositionstart → compositionend → blur`，保存按钮恢复可用，写请求 0。该结果只覆盖合成事件与浏览器引擎，未使用系统拼音候选窗口。

Chrome 执行文件为本机 Google Chrome，应用包版本 `155.0.8059.85`；该次审查未输出 CDP Browser 版本字段。私密审查工件标识 `IME-AUTO-20261026-CDP-NAV-01`，脚本保留在 `/var/folders/82/xbj2snf53jnft554879gqplh0000gn/T/lifearchive-ime-audit-QvgrEW/audit.mjs`。审查退出码 0，关闭了临时服务、WebSocket 和 Chrome，无长驻审查服务。

[CI run 40211516968](https://github.com/GZY-q/LifeArchive/actions/runs/40211516968) 对准备提交 `b2d2398c9d649601f8c38fa2fb61d2ee6670e02f` 的 backend/frontend/compose/restore 四项全部通过：200 个真实 PG 测试、20 个脚本测试、97 个前端测试，共 **317 项**。37 项专项属于前端 97 项子集，不重复计数。真实 Chrome 应用回归、导出、正常恢复和损坏备份拒绝同时通过；这些结果仍不填写真实输入法矩阵。

## 本轮桌面手测环境

主代理新建了独立合成数据库 `life_archive_ime_smoke_3b94b9a07d`，迁移至 `0003_journal`，通过 CLI 初始化临时 owner。没有复用原预览库或导出/恢复样本库；初始化没有创建日记。

| 入口 | 当前本机地址/状态 |
| --- | --- |
| Web | `http://127.0.0.1:18086/`，Caddy 提供当前 dist |
| API | `127.0.0.1:18882`，只由该测试 Web 同源代理 |
| PG | 既有临时 PG 的 `127.0.0.1:25432`，独立 DB 名称如上 |
| 账号/密码 | 仓库外私密 credentials.json（不复制到 Git/日志/截图） |
| 缓存目录 | `/Users/gede/.cache/lifearchive-ime-validation-mds2mjy1`，0700；凭据/配置 0600 |

API 信任本机 18086 的精确 Origin，HTTP cookie 仅用于该 loopback 合成实例。Caddy 配置显式 `bind 127.0.0.1`，已通过实际监听检查；站点 URL 的 hostname 不能替代监听绑定。health 返回 ok，未放宽全局登录限流。

该 URL 只适用于当前 Mac。同一浏览器中不同端口的 cookie 可能互相影响，建议用本次测试专用浏览器 profile/窗口，测试期间避免登录其他 LifeArchive 本机实例。Windows 使用其本机的独立 loopback 实例；手机需要另行配置已授权的测试 HTTPS 入口，不能直接把此 loopback URL 当作手机可用入口。

本机服务停止后的准确重启命令位于上述私密缓存的 `HANDOFF.md`。先检查端口和 PG 状态，运行中不启动第二份；不重置 owner 或删除数据库以重试。其他机器按 [M1 隔离部署](m1-handoff.md#精确运行与测试) 使用专用项目、端口、owner 和合成数据，不使用正式日记实例。

## 手工结果接续

用户先执行 macOS Safari 的中文候选/保存/历史/导航子集，再以同样协议测 Chrome。后续需确认设备型号、系统/浏览器/输入法版本、布局、逐项实际表现及证据标识；把简单“正常”反馈拆成确实执行的用例，不把未执行步骤标成通过。

对已保存的合成记录，可在此专用库中用记录 ID、内容和修订比较/哈希补充证据；不要对真实日记库做读取或故障注入。C03 两标签使用同一现有会话，C05 验证失效/恢复，C06 仅在此实例丢弃一次成功创建响应并复核相同请求 UUID。细节见协议。

如发现可稳定复现的小缺陷，先保存步骤和输入事件/原文证据，再在现有模块最小修复并增加回归。无缺陷时保持实现；本片没有引入 Memos、依赖、API、迁移、存储变更、自动保存或磁盘草稿。

只有全部最低组合的关键用例有真实操作证据且无原文丢失/重复保存问题，才可宣布兼容验收完成。可以交付已验证子集和明确缺口；不能因 CI 绿色就完成真机门槛。未安排的 iOS/Android 行仍待验证，后续功能也需要独立分配工单。
