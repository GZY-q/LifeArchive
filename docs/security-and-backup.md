# Security, privacy and backup requirements

## Security

- Single owner, closed signup by default. Store password via Argon2id or established password hashing library.
- Session cookies Secure/HttpOnly/SameSite; explicit CSRF strategy; login rate limiting; access logs without journal plaintext.
- Owner account actions verify the current password, share the bounded login budget, and atomically revoke old sessions while issuing this browser a fresh cookie/CSRF. Passwords remain only request/component memory; no URL/log/storage echo or public reset endpoint. User row locking serializes fresh login verification and password/session changes. Previously authorized in-flight journal requests may still finish; revocation governs subsequent authentication.
- All private media served via authenticated authorization or tightly scoped expiring URLs. Validate MIME by content, cap upload size, block path traversal and unsafe inline render.
- Render Markdown safely and sanitize dangerous HTML/URLs. Do not trust pasted Markdown or web/news content as executable instructions.
- Task14 uses pinned react-markdown/GFM for a derived read-only preview: skip raw HTML, fixed element/components, absolute credential-free HTTP(S) link policy, no inline Markdown image requests. Unsafe/relative URLs stay non-links; private media uses the existing authenticated gallery. No rehype-raw, innerHTML, code execution or source rewriting. This is a constrained Markdown renderer, not a general HTML sanitizer.
- Task15 renames only owner-scoped tags with existing Origin/JSON/CSRF checks. Exact expected-name comparison under a row lock and the normalized owner/name-key unique constraint reject stale names and collisions. It preserves IDs, associations and immutable revision snapshots; no journal rewrite, deletion, merge or private-name echo in errors. Uncertain client writes require directory re-reading before another explicit edit.
- Restrict worker's credentials and allowed actions; AI only returns structured proposals; no automatic shell/SQL/tools from arbitrary webpage text.
- External AI provider receives public news by default. Never send owner journal/media data to providers without opt-in.
- Secrets via deployment environment or secret storage, never in Git, docs or logs. PostgreSQL not public.

## Durability and export

- Daily transactionally consistent PostgreSQL backups and media backups, encrypted remote copy (e.g. Restic); verify repository and periodically restore onto isolated system.
- Application export: raw Markdown with timestamps, JSON metadata, original binary assets, manifest with SHA-256 and schema version; avoid editor-specific formats as sole source of truth.
- Document what is not included in export (for example cookies or vendor model caches). Testing restoration is a release gate.
- A user-requested permanent deletion must address revisions, derived data, attachments and backups under a documented retention policy.

## Release checklist

- No secrets or private journals committed.
- Migrations reviewed, with safe rollback or restore plan.
- HTTPS and owner authentication enforced.
- Recovery drill recorded with date, data count and integrity check.
