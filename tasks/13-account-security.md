# 13 — 账户密码修改与会话撤销

用户继续功能开发，推进12交接规划。基于`codex/journal-pinning`的`9a72e2cfde407664380424fad56196bc4ae4d470`堆叠交付，子代理分工、减少测试，不自动合并前序PR。保留用户`.DS_Store`、日记/原图、18086环境；07真机输入法仍待证据。无新服务/迁移/依赖，head仍0006、导出仍v4。

## 固定接口

- `POST /api/v1/auth/password`：JSON `{current_password,new_password}`，成功200返回现有AuthResponse并轮换HttpOnly/SameSite/Secure配置一致的新cookie/CSRF。两者SecretStr、不回显；当前密码1–1024，新密码15–1024 Unicode字符，拒绝纯空白/NUL，不trim或Unicode归一化；新旧相同422/code password_unchanged。
- `POST /api/v1/auth/sessions/revoke`：JSON `{current_password}`，验证后撤销所有旧会话并给当前浏览器新会话，200 AuthResponse；不改密码。UI称“退出其他会话”，当前旧token也撤销、以新token接续。
- 两接口有效会话+可信Origin+X-LifeArchive-Request:1+JSON+CSRF必需，未知字段/格式错误通用422。当前密码错误403/code invalid_current_password，不误判为会话过期；无效/已撤销/过期会话401，CSRF/Origin错误403，非JSON415。
- 共用现有全局登录尝试预算（每300秒5次，成功和失败均计数），在昂贵hash前持久化预留，超限429+Retry-After，不新增可绕过登录限制的猜密码通道；失败不更改密码或会话。
- 密码更新、全部旧sessions revoked_at、新session创建在同一事务提交，不保存明文密码或原token，不删除认证记录。没有公开找回/邮件/重置CLI/后门、会话列表或设备识别。

## 并发边界

复用User行锁：普通登录authenticate也先锁owner并populate_existing，再验证最新hash，锁保留到创建session提交；避免旧密码登录在密码修改后补建有效会话或rehash覆盖新密码。敏感操作在预算预留commit后重新锁定/刷新owner，并在锁内再次核对发起操作的session仍有效，再验证当前密码/更新hash/撤销/轮换。失效的在飞操作返回401，不能通过早先依赖鉴权越过撤销。所有路径失败显式回滚释放锁，预算不回滚。

撤销阻止之后的鉴权，不承诺撤回已通过鉴权的普通日记在飞请求；不把此片扩展为全部业务写入的令牌锁框架。

## 前端

认证内增加“账户”入口（可放账号栏，避免拥挤主导航）；提供当前/新/确认新密码表单与单独“退出其他会话”操作，明确会撤销其他浏览器登录。新密码前端同样15–1024字符、确认匹配，password input正确autocomplete；只在组件内存中持有，提交结束/卸载清空，不记日志、不进URL/持久存储/草稿。

用全局onBusy锁定导航/退出/验证与其他写入，禁止重复提交。成功将返回Session交给AuthGate.acceptLogin同owner更新cookie对应CSRF，不触发初始检查或重挂日记，保留正文/标签/图片/冻结UUID/409；后续写入用新CSRF。401沿用expire保留草稿；403当前密码错误独立文案，不自动退出。

网络结果不确定不自动重试或显示成功，清空密码输入并提示先验证登录/必要时用新密码重登核对；在重新验证或重登前禁敏感表单再提交。当前cookie也可能已轮换，不能盲用旧CSRF重发。离开账户时敏感字段不保留，日记草稿继续内存保护。

## 交付与必要检查

代码、少量关键真实PG与前端用例、接口/安全/交接/精确命令和独立PR。只覆盖当前密码验证、旧密码/旧token/旧CSRF失效、新会话可用、预算和并发锁边界、草稿/冻结请求保留；不追加本机全量/浏览器/恢复演练。

预览仅重启18088自己的API加载代码，不对既有owner执行改密/撤销动作，不重置凭据或改动真实会话；行为验证仅在专用测试库新schema合成账户进行。下一片只规划。
