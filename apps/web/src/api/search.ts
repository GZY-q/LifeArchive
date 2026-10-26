import { invalidResponse, isRecord, request } from './client';
import { entryFrom } from './journal';
import type { Entry } from './journal';

export type SearchFilters = {
  query: string;
  date_from: string | null;
  date_to: string | null;
  tag_id?: string | null;
};

export async function searchEntries(
  filters: SearchFilters,
  csrfToken: string,
  cursor: string | null = null,
  signal?: AbortSignal,
): Promise<{ items: Entry[]; next_cursor: string | null }> {
  // Keep private search text out of URLs, browser history, and access logs.
  const value = await request('/search', {
    method: 'POST',
    body: { ...filters, limit: 20, cursor },
    csrfToken,
    signal,
  });
  if (
    !isRecord(value) ||
    !Array.isArray(value.items) ||
    !(
      value.next_cursor === null ||
      (typeof value.next_cursor === 'string' &&
        value.next_cursor.length > 0 &&
        value.next_cursor.length <= 2048)
    )
  )
    return invalidResponse();
  return { items: value.items.map(entryFrom), next_cursor: value.next_cursor };
}
