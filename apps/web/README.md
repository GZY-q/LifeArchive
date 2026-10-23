# LifeArchive Web · M0

仅实现品牌首页、不可用的后续导航占位和 API 连接检查。没有日记编辑、登录、路由、持久化、新闻或 AI 功能。完整部署与验收步骤见仓库根目录 `README.md`。

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

| 文件                                 | 职责                                   |
| ------------------------------------ | -------------------------------------- |
| `src/App.tsx`                        | 当前首页与导航占位，后续页面从这里接入 |
| `src/api/health.ts`                  | 同源健康请求及响应校验                 |
| `src/components/HealthIndicator.tsx` | 请求状态、8 秒超时、取消与手动重试     |
| `src/styles.css`                     | 移动端适配、键盘焦点和基础视觉样式     |
| `src/App.test.tsx`                   | 首页和连接状态的行为测试               |
| `vite.config.ts`                     | 开发代理、Vitest 配置                  |

健康响应约定为 HTTP 2xx 且 JSON `{ "status": "ok" }`；它只说明 API 可响应，不代表数据库、鉴权或全部功能可用。前端不展示服务内部错误信息。请求仅在挂载或用户手动检查时触发，没有后台轮询。

测试覆盖初始加载、成功、HTTP 错误、错误结构、非 JSON、网络错误后重试和超时。M1 才开始日记与登录，需重新阅读 `tasks/01-journal.md`，明确会话与 CSRF 策略后再接私有接口；编辑器必须先核验 React、中文输入法和移动端兼容性。

## 依赖依据

2026-10-23 核验 npm 正式版本与以下官方文档。React/Vite 使用当前稳定版本；TypeScript 固定 6.0.3，以满足 `typescript-eslint` 的 `<6.1` peer 约束。M0 用少量普通 CSS，暂不引入 Tailwind、组件库或编辑器。

- [Vite 环境要求](https://vite.dev/guide/)
- [Vite 开发代理](https://vite.dev/config/server-options#server-proxy)
- [Vitest 环境与配置](https://vitest.dev/guide/)
- [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
