# Paste this into Codex after importing the repository

你是 LifeArchive 项目的首位工程实现者。请先阅读仓库根目录的 `AGENTS.md`、`README.md`、`docs/product.md`、`docs/architecture.md`、`docs/data-model.md`、`docs/roadmap.md`，然后严格按照 `tasks/00-foundation.md` 实施 **M0 项目基础设施**。

要求：
1. 只做 M0，不提前开发日记功能、新闻 Agent、AI、登录业务或长期 roadmap 项目。
2. React + Vite + TypeScript 前端，FastAPI 后端，PostgreSQL，Docker Compose，Caddy 静态服务和 API 反向代理。Worker 与 API 共享镜像，但 M0 不引入无意义常驻循环。
3. 建立最小可维护的目录、依赖锁文件、Alembic、基础健康检查、单元测试、lint/build 命令、`.env.example` 和清晰 README。
4. 绝不将真实密钥写入 Git，也不暴露 PostgreSQL 公网端口。
5. 完成后请运行可以执行的检查；清楚报告每项执行结果及环境阻塞，不得假称通过。
6. 最终请提供变更摘要、目录结构、启动指令、验证清单和建议下一张工单，并通过 Pull Request 交付。

请先简要说明你的 M0 实施计划，然后直接实施。
