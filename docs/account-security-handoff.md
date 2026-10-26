# 13 账户安全交接

范围见 [13工单](../tasks/13-account-security.md)。分支`codex/account-security`从`codex/journal-pinning`的`9a72e2cfde407664380424fad56196bc4ae4d470`堆叠交付，不合并前序PR。07真机输入法仍待人工证据；本片不开发新闻/AI。

## 使用与运行

登录后点账号栏“账户”。改密须填写当前/新/确认新密码；“退出其他会话”只需当前密码、不改密码。两个动作都会撤销全部旧会话，当前浏览器收到新cookie/CSRF后继续使用。日记草稿、图片选择、冻结创建UUID和409状态不被重置。

新密码15–1024字符，保留原空格和Unicode，不trim/归一化；拒绝纯空白/NUL/新旧相同和非法Unicode。密码字段仅组件内存，提交结束或离开清空，应用不放URL/日志/浏览器持久存储。网络结果不确定不自动重试或假定成功，跨导航保持敏感操作锁；先“重新验证登录”，如已失效则用新密码重登核对，原草稿仍在同页。403当前密码错只提示重输，不自动退出。

已有实例从仓库根目录运行：

```bash
docker compose up -d --build --wait
docker compose exec -T api alembic current
```

没有新迁移、依赖或配置，head仍`0006_journal_pinning`、导出v4不变。更早版本按根README显式升级迁移，不重置owner。没有公开找回、邮件、重置CLI/后门；init-owner仍拒绝覆盖已有账户。

本机 [18088预览](http://127.0.0.1:18088/)沿用原owner/数据库/原图，仅重启自己的API加载代码。私密启动说明和0600凭据在`/Users/gede/.cache/lifearchive-tags-dev-qockdezn`，不提交密码。本轮没有替预览owner改密码或撤销真实会话；18086旧环境保持不动。行为检查只在专用PG随机schema的合成账户进行。

## 接口与事务边界

- `POST /auth/password {current_password,new_password}`与`POST /auth/sessions/revoke {current_password}`，认证、JSON、Origin、X-LifeArchive-Request:1和CSRF必需，成功200 AuthResponse+新会话cookie；cookie配置复用登录helper。
- 两接口和普通登录共享每300秒5次预算，hash前预留并commit；成功/失败都计数，429含Retry-After。当前密码错误403/invalid_current_password；新旧相同422/password_unchanged，其他格式错误通用422，不回显输入；失效token401。
- `auth/service.py`：普通authenticate锁User并populate_existing，验证新hash后一直持锁到session提交，避免旧密码并发登录/rehash覆盖新hash。敏感操作先预算commit，再按User→当前AuthSession的顺序加行锁，刷新身份映射、按实际clock_timestamp复核session，再验证密码、改hash（可选）、撤销旧session、新建并提交一个替代session。logout只拿session行锁，不反向取User锁。
- 锁内复核防先前鉴权绕过撤销、等锁期间过期、并发改密重复通过。失败回滚释放锁，预算已持久化不回退。会话行保留，不删除认证记录；原token不存DB，密码仅存Argon2id hash。
- 撤销阻止之后的鉴权，不撤回此前已获授权的普通日记在飞请求。无新auth版本框架或业务写入全局锁，避免扩大范围。
- `api/auth.ts`、`auth/AccountWorkspace.tsx`与`AuthGate.tsx`：新Session走同owner acceptLogin，更新后续CSRF，不触发初始检查/重挂编辑器。未知结果锁在AuthGate跨导航保留，验证/重登成功才解除；组件忽略卸载后晚响应，避免恢复私密DOM。
- 日记、修订、标签、图片、置顶和导出格式不受影响；认证hash/session仍不进入可移植应用导出。

## 必要验证

遵循“减少测试，先开发功能”，只运行新增关键用例与静态检查：

- 真实PG `tests/auth/test_account_security.py` **4项通过（1.06秒）**：改密后旧密码/旧cookie/旧CSRF失效、新会话可用且原文历史不变；单独撤销/错误密码/字段和Unicode/共享预算；缓存旧owner的并发登录与改密；并发变更只有一个通过、会话过期复核。
- 前端typecheck、lint、修改文件格式化与 `auth/AccountWorkspace.test.tsx` **2项通过（586毫秒）**：新CSRF与冻结图片草稿/UUID接续、密码清空、403、未知结果跨导航锁/验证、401重登草稿。
- 限定4个后端文件Ruff检查/格式检查通过；只读子代理核对锁序、实际DB时钟、未知锁和晚响应保护。最终User+Session锁已人工确认，不追加全量测试。

未运行本机全量回归、镜像构建、浏览器、恢复或真机演练；当前功能CI由新PR自动触发，前序成功不替代本片结果。

后续只读查询确认：提交`41276cf8ef46d4d6a6aa4f571ead1c72efe92623`的[CI 40323383358](https://github.com/GZY-q/LifeArchive/actions/runs/40323383358)已全部成功；本机未追加全量检查。此结果只属于13，不代表后续Markdown预览。

最小复核（PG环境私密注入TEST_POSTGRES_*，缺配置skip不等于通过）：

```bash
cd apps/server
uv run --locked pytest -q tests/auth/test_account_security.py
cd ../web
npm run typecheck
npm run lint
npm test -- --run src/auth/AccountWorkspace.test.tsx
```

## 下一片建议

14建议安全Markdown只读预览：选测试过并固定版本的库，禁原始HTML和危险URL/远程图片，原文和现IME适配不改写，私密图片继续现有图库。先写有界工单，不重构编辑器或调用外部AI。接手模型复用认证/Session/草稿边界，不新增服务或重置用户数据。
