# Product specification — LifeArchive V1.0

## Vision

“记录我生活的每一天，也记录世界在这一天发生了什么。”

## Personas and deployment

- Start with one owner on a private VPS, responsive web/PWA style interface.
- No public registration, social feed, group collaboration, or mobile-native apps in V1.0.
- User owns data and can export it without vendor-specific editor format.

## Day-to-day flows

1. Open home; start writing immediately; markdown is stored verbatim.
2. Attach images, tag notes, optionally adjust diary date; save/auto-draft safely.
3. Browse feed, calendar, and a day-specific Daily Capsule.
4. Daily Capsule shows journal entries and independently curated world events, each with traceable sources.
5. Search by date, tags, and keywords; 'On this day' surfaces prior years once records exist.

## V1.0 required features

- Owner login, secure sessions and private access.
- Journal CRUD, pagination, tags, attachments, pinning, edit revision history, trash/restore, optional date correction.
- Timeline/list/calendar/day detail; mobile first layout.
- News source configuration, RSS/API fetch, deduplication, event clustering, global/AI/interest selection, structured LLM summary, cited daily digest, ability to re-run jobs.
- Basic keyword/date/tag search; not semantic RAG yet.
- Markdown/JSON + original assets export, automated backup and tested restoration.

## Future roadmap (not V1.0)

- V1.1: semantic + temporal hybrid search with citations; cross-event linking requiring approval.
- V1.2: evidence-based annual memoir and event follow-up timelines.
- V2: optional graph views, richer offline support or shared accounts.

## Product guardrails

- No streak pressure, mood scoring, forced daily prompts or unverified personal inferences.
- News events and journal are *different record types*; time proximity is not causal evidence.
- AI can create suggestions/annotations, not mutate original journal content.
- The app must function for journal creation and reading without AI connectivity.
