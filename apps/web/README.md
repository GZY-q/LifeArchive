# LifeArchive Web · M2 归档搜索

实现 owner 登录、日记录入/列表/编辑/删除确认、版本比对和修订历史，以及月历计数、日期详情和归档搜索。切换日历/归档时保留日记组件与内存草稿；会话失效时移除所有视图的私密 DOM，重新登录可继续同页草稿。完整部署和边界见根 README 与 `docs/m2-search-handoff.md`。

## 本地开发

使用 `.node-version` 中的 Node.js 24.19.0 和 `packageManager` 中的 npm 11.17.0。以下命令在 `apps/web` 目录运行：

```sh
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173`。开发服务器默认将 `/api` 代理到 `http://127.0.0.1:8000`，需先按根目录说明启动后端。更换开发 API 地址：

```sh
API_PROXY_TARGET=http://127.0.0.1:8080 npm run dev
```

`API_PROXY_TARGET` 是 Vite 开发服务器环境变量，不进入客户端构建；生产环境统一通过 Caddy 同源代理。不要将密钥放入 `VITE_*` 变量。

依赖默认为中国大陆 npm 镜像，直接依赖锁定精确版本，完整依赖树由 `package-lock.json` 固定。使用 `npm ci` 安装，不在开发任务中顺手升级依赖。

镜像不可用时，可运行 `npm ci --registry=https://registry.npmjs.org/`。项目的 `replace-registry-host=always` 让已锁定的下载地址跟随选定仓库；包版本与完整性校验保持不变。

## 质量检查

```sh
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build
```

`npm run format` 格式化前端文件；`npm run test:watch` 持续运行测试。构建结果位于 `dist/`。`npm run preview` 只用于本地预览构建，完整部署请使用 Compose/Caddy。

## 后续实现入口

| 文件                                 | 职责                                              |
| ------------------------------------ | ------------------------------------------------- |
| `src/App.tsx`                        | 应用外壳与健康指示                                |
| `src/auth/`                          | 登录边界、认证内导航、重新验证和显式退出          |
| `src/api/`                           | typed 同源客户端、响应校验、15 秒超时、CSRF       |
| `src/journal/`                       | 日期、创建重试 UUID、列表、409 草稿比对与修订历史 |
| `src/calendar/`                      | 公历日期运算、月历和分页日期详情                  |
| `src/search/`                        | 搜索表单、已提交条件快照、分页/重试与竞态取消     |
| `src/components/MarkdownEditor.tsx`  | 受控原文适配、IME composition 状态                |
| `src/api/health.ts`                  | 同源健康请求及响应校验                            |
| `src/components/HealthIndicator.tsx` | 请求状态、8 秒超时、取消与手动重试                |
| `src/styles.css`                     | 移动端适配、键盘焦点和基础视觉样式                |
| `src/App.test.tsx`                   | 首页和连接状态的行为测试                          |
| `vite.config.ts`                     | 开发代理、Vitest 配置                             |

健康响应约定为 HTTP 2xx 且 JSON `{ "status": "ok" }`；它只说明 API 可响应，不代表数据库、鉴权或全部功能可用。前端不展示服务内部错误信息。请求仅在挂载或用户手动检查时触发，没有后台轮询。

测试覆盖健康状态、登录与 401、CSRF、会话重新验证、创建结果不确定时的 UUID 重试、中文组合输入、补记、409 草稿保护、删除确认、分页和修订安全显示。M2 第一片还覆盖月历/单日请求竞态与重试、跨视图保留草稿/UUID/冲突状态、时区默认值及 1–9999 年公历边界。真实 Chrome 运行 `scripts/smoke-browser.mjs`，验证真实 API、日期计数、原文、草稿和桌面/手机尺寸布局。

归档只在明确提交后读取；关键词、日期与游标只放 POST 请求体。输入变化不修改已有结果对应的已提交条件，翻页/重试沿用该快照。离开归档会取消请求并卸载结果，返回保留内存表单，需再次提交。显式退出清空表单，不使用 URL 或浏览器持久存储；原文按纯文本显示。测试覆盖这套状态边界、请求竞态、CSRF、401 和草稿保护。

M1 未引入 `@usememos/editor`。已核验其正式 `26.10.25` 包存在、MIT、React peer >=18；上游仍要求真实系统 IME / 移动软键盘矩阵，因此本轮使用独立 textarea 适配层。详见 [编辑器选择记录](../../docs/m1-handoff.md)。不要将 Chrome 模拟的 composition 事件声称为全部真实键盘通过。

## 依赖依据

沿用 M0 已锁定的 React/Vite 依赖，M1 和 M2 两片均不额外升级前端依赖。TypeScript 固定 6.0.3，满足 `typescript-eslint` 的 `<6.1` peer 约束；布局使用普通 CSS。依赖与设计参考：

- [Vite 环境要求](https://vite.dev/guide/)
- [Vite 开发代理](https://vite.dev/config/server-options#server-proxy)
- [Vitest 环境与配置](https://vitest.dev/guide/)
- [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
