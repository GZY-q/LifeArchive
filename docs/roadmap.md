# Development roadmap and acceptance gates

## Milestones

### M0 — repository foundation (first Codex task)
- Monorepo React/Vite TS + FastAPI + PostgreSQL, Docker Compose, Caddy (development-friendly), health endpoint, Alembic foundation, lints/test scaffolding, README run instructions.
- Acceptance: from clean clone, `docker compose up -d --build`, `/api/v1/health` returns JSON; PostgreSQL persists after restart; basic frontend loads; test/lint commands documented and pass.
- No journal CRUD, news, auth or AI in M0.

### M1 — journal essentials
- Closed-owner login, Markdown editor adapter, entry CRUD with optimistic revision/creation idempotency, tags, list and day grouping. Add assets and edit history in prioritized slices.
- Acceptance: journal works when worker/LLM disabled; mobile inputs work including Chinese IME; data persists across restart; tests pass.

### M2 — archive/day views
- Calendar month, Daily Capsule with journal side; basic search, timezone correctness, `On this day`.
- Acceptance: date assignment and late-backfill work without confusing creation date.

### M3 — news ingestion
- RSS/API sources, source metadata, dedup, event association, job ledger, retries and observability.
- Acceptance: a week of replayable sample fixtures doesn't create duplicates or lose provenance.

### M4 — LLM-curated digests
- LLM adapter, prompt/schema version, structured summary, strict source references, versioned daily digest, interest filtering.
- Acceptance: can re-run a day safely, list cited sources, and operate journal without AI availability.

### M5 — VPS reliability release
- Hardened Caddy/Compose, access controls, private media, encrypted offsite backups, export, verified restore, docs.
- Acceptance: cold restore onto a fresh environment with journal/media/news continuity.

## Execution agreement

One milestone is not one giant PR. Keep PRs small and independently testable. Do not implement next milestone until the current task's acceptance checks pass.

## 当前交付顺序与待分配计划

本段是当前实施快照，保留上面的 M0–M5 总路线，不将局部切片称为整个里程碑完成。

- M0 已合入 main；M1 安全日记核心 PR #2 和 M2 月历/日期 PR #3 待审阅合入，后者依赖前者。
- 本轮执行 `tasks/03-archive-search.md`，搜索 PR #4 基于 `codex/m2-calendar-days`。先依次审阅合入依赖，再核对后继 PR 的 base、差异与 CI；不自动合并。
- 后续建议每次明确分配一个 PR：`04-on-this-day` → `05-journal-export` → `06-restore-rehearsal` → `07-editor-compatibility`。这四张工单目前仅为规划，未实施。
- 05/06 提前验证最小原文/修订可携带与隔离恢复门槛；完整定时加密异地备份、私密媒体和生产冷恢复仍属 M5。真实 IME 验证、标签/附件等 M1 缺口继续单独列账，不能宣称 M1 已全部完成。
- 新闻摄取 M3、AI 摘要 M4 的顺序和架构保持不变，但不属于上述近期待分配切片。

依赖、具体 API/CLI、验收门槛、禁止扩展的范围与接手提示词见 [后续实施计划](next-steps.md)。
