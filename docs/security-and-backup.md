# Security, privacy and backup requirements

## Security

- Single owner, closed signup by default. Store password via Argon2id or established password hashing library.
- Session cookies Secure/HttpOnly/SameSite; explicit CSRF strategy; login rate limiting; access logs without journal plaintext.
- All private media served via authenticated authorization or tightly scoped expiring URLs. Validate MIME by content, cap upload size, block path traversal and unsafe inline render.
- Render Markdown safely and sanitize dangerous HTML/URLs. Do not trust pasted Markdown or web/news content as executable instructions.
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
