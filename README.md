# LifeArchive

> Personal journal × world history × trustworthy AI memory.

LifeArchive 是一个独立实现、单用户优先、自托管、面向几十年持续保存的个人记忆系统。日常记录体验借鉴 Memos，但**不依赖 Memos 服务**；AI 采用内置固定工作流，**不依赖 Hermes**。

## 当前状态

- 当前仓库的文档是 V1.0 **开发交接规范**，不是已完成产品。
- 先执行 `tasks/00-foundation.md`，再执行 `tasks/01-journal.md`。
- 所有设计取舍以 `docs/architecture.md`、`docs/product.md` 和 `docs/data-model.md` 为准。发生冲突时，先在 PR 中指出差异，不要静默改动核心约束。

## 目标

1. 5 秒内开始写日记：Markdown、标签、照片、补记、历史版本。
2. 每日世界新闻自动归档：全球要闻、科技/AI、自定义兴趣，带来源和版本。
3. 个人日记和世界事件围绕“日”聚合形成 Daily Capsule。
4. 日后支持可追溯的检索、年度回忆录与事件关联。
5. 即使 AI 和外部服务失效，日记仍然可以独立工作；数据始终可导出与恢复。

## 核心栈

- Web: React + Vite + TypeScript；Tailwind CSS / shadcn/ui；优先封装 `@usememos/editor`（核验兼容与许可证并锁版本）。
- API: FastAPI、Pydantic、SQLAlchemy 2、Alembic。
- Database: PostgreSQL；时间相关字段规范化；保留用户本地日期。
- Worker: 与 API 同一个 Python 代码库和镜像，不同启动命令；APScheduler 3.x 负责触发；数据库任务表负责持久化、重试和幂等。
- AI: 可更换的 LLM Adapter，结构化输出 + 服务端校验；不允许 LLM 任意 SQL / Shell 操作。
- Infra: Caddy、Docker Compose、私有媒体存储，后期 Restic 异地备份。

## 从零开始

该交接包**不包含运行代码**。先让 Codex 完成基础设施任务，提交 PR，审查后再开始日记功能。

Codex 第一条指令在 `CODEX_FIRST_PROMPT.md`。

## 文档导航

- `AGENTS.md` — 给 Codex 的长期规则（保持短小）
- `docs/product.md` — 产品目标、功能范围、用户体验
- `docs/architecture.md` — 组件与数据流、部署原则
- `docs/data-model.md` — 数据域、关键约束和扩展策略
- `docs/api-contract.md` — V1 API 草案
- `docs/security-and-backup.md` — 隐私、安全、备份恢复
- `docs/roadmap.md` — 里程碑、验收标准
- `tasks/00-foundation.md` — 第一张可执行工单
- `tasks/01-journal.md` — 第二张可执行工单
- `docs/decisions.md` — 核心技术决策

## 免责声明

文档包含未来目标与草案，不能当作已实现功能。许可证信息与第三方依赖版本须在实际引入时核验，所有密钥必须通过运行环境配置，禁止进入 Git。
