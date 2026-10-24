# LifeArchive Web · M1

实现 owner 登录、日记录入/列表/编辑/删除确认、版本比对和修订历史，以及健康指示。草稿仅在页面内存；会话失效时隐藏私密 DOM，重新登录可继续同页草稿。完整部署和边界见根 README 与 `docs/m1-handoff.md`。

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
| `src/App.tsx`                        | 当前首页与导航占位，后续页面从这里接入            |
| `src/auth/`                          | 登录边界、重新验证和显式退出                      |
| `src/api/`                           | typed 同源客户端、响应校验、15 秒超时、CSRF       |
| `src/journal/`                       | 日期、创建重试 UUID、列表、409 草稿比对与修订历史 |
| `src/components/MarkdownEditor.tsx`  | 受控原文适配、IME composition 状态                |
| `src/api/health.ts`                  | 同源健康请求及响应校验                            |
| `src/components/HealthIndicator.tsx` | 请求状态、8 秒超时、取消与手动重试                |
| `src/styles.css`                     | 移动端适配、键盘焦点和基础视觉样式                |
| `src/App.test.tsx`                   | 首页和连接状态的行为测试                          |
| `vite.config.ts`                     | 开发代理、Vitest 配置                             |

健康响应约定为 HTTP 2xx 且 JSON `{ "status": "ok" }`；它只说明 API 可响应，不代表数据库、鉴权或全部功能可用。前端不展示服务内部错误信息。请求仅在挂载或用户手动检查时触发，没有后台轮询。

测试覆盖健康状态、登录与 401、CSRF、会话重新验证、创建结果不确定时的 UUID 重试、中文组合输入、补记、409 草稿保护、删除确认、分页和修订安全显示。真实 Chrome 还会运行 `scripts/smoke-browser.mjs`，验证真实 API 与布局。

M1 未引入 `@usememos/editor`。已核验其正式 `26.10.25` 包存在、MIT、React peer >=18；上游仍要求真实系统 IME / 移动软键盘矩阵，因此本轮使用独立 textarea 适配层。详见 [编辑器选择记录](../../docs/m1-handoff.md)。不要将 Chrome 模拟的 composition 事件声称为全部真实键盘通过。

## 依赖依据

沿用 M0 已锁定的 React/Vite 依赖，M1 不额外升级前端依赖。TypeScript 固定 6.0.3，满足 `typescript-eslint` 的 `<6.1` peer 约束；布局使用普通 CSS。依赖与设计参考：

- [Vite 环境要求](https://vite.dev/guide/)
- [Vite 开发代理](https://vite.dev/config/server-options#server-proxy)
- [Vitest 环境与配置](https://vitest.dev/guide/)
- [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
