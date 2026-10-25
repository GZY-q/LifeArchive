import { vi } from 'vitest';

import type { Session } from '../api/auth';
import type { Entry } from '../api/journal';

export const session: Session = {
  user: { id: 'owner-id', username: 'owner', timezone: 'Asia/Shanghai' },
  csrf_token: 'test-csrf-token',
};

export const sampleEntry: Entry = {
  id: 'entry-id',
  content_md: '# 原文\n\n今天的记录。  \n',
  entry_date: '2026-10-01',
  revision: 1,
  created_at: '2026-10-02T03:00:00Z',
  updated_at: '2026-10-02T03:00:00Z',
  tags: [],
};

export function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

type Handler = (
  path: string,
  options: RequestInit,
) => Response | Promise<Response> | undefined;

export function mockApi(
  handler: Handler = () => undefined,
  entries: Entry[] = [],
) {
  const fetchMock = vi.fn(async (path: string, options: RequestInit) => {
    const result = handler(path, options);
    if (result !== undefined) return await result;
    if (path === '/api/v1/health') return json({ status: 'ok' });
    if (path === '/api/v1/auth/me' || path === '/api/v1/auth/login')
      return json(session);
    if (path.startsWith('/api/v1/entries?'))
      return json({ items: entries, next_cursor: null });
    if (path.startsWith('/api/v1/tags?'))
      return json({ items: [], next_cursor: null });
    throw new Error(
      `Unexpected test request: ${options.method ?? 'GET'} ${path}`,
    );
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

export function requestBody(options: RequestInit): Record<string, unknown> {
  return JSON.parse(String(options.body)) as Record<string, unknown>;
}
