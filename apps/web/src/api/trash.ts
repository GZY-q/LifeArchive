import { invalidResponse, isRecord, request } from './client';
import { entryFrom } from './journal';
import type { Entry } from './journal';

export type TrashEntry = Entry & { deleted_at: string };

export async function listTrash(
  cursor?: string,
  signal?: AbortSignal,
): Promise<{
  items: TrashEntry[];
  next_cursor: string | null;
}> {
  const query = new URLSearchParams({ limit: '20' });
  if (cursor) query.set('cursor', cursor);
  const value = await request(`/trash?${query}`, { signal });
  if (
    !isRecord(value) ||
    !Array.isArray(value.items) ||
    !(value.next_cursor === null || typeof value.next_cursor === 'string')
  )
    return invalidResponse();
  return {
    items: value.items.map((item: unknown) => {
      if (
        !isRecord(item) ||
        typeof item.deleted_at !== 'string' ||
        !Number.isFinite(Date.parse(item.deleted_at))
      )
        return invalidResponse();
      return { ...entryFrom(item), deleted_at: item.deleted_at };
    }),
    next_cursor: value.next_cursor,
  };
}

export async function restoreEntry(
  entry: TrashEntry,
  csrfToken: string,
): Promise<Entry> {
  return entryFrom(
    await request(`/entries/${encodeURIComponent(entry.id)}/restore`, {
      method: 'POST',
      body: { expected_revision: entry.revision },
      csrfToken,
    }),
  );
}
