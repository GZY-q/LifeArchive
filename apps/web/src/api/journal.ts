import { invalidResponse, isRecord, request } from './client';
import { tagLabelsFrom } from './tags';
import type { TagLabel } from './tags';

export type Entry = {
  id: string;
  content_md: string;
  entry_date: string;
  revision: number;
  created_at: string;
  updated_at: string;
  tags: TagLabel[];
};
export type EntryRevision = Pick<
  Entry,
  'content_md' | 'entry_date' | 'revision' | 'tags'
> & {
  changed_at: string;
  editor_id: string;
};
export type EntryInput = Pick<Entry, 'content_md' | 'entry_date'> & {
  tag_ids: string[];
};
export type CreateInput = EntryInput & { client_request_id: string };

export function entryFrom(value: unknown): Entry {
  if (
    !isRecord(value) ||
    typeof value.id !== 'string' ||
    typeof value.content_md !== 'string' ||
    typeof value.entry_date !== 'string' ||
    !Number.isInteger(value.revision) ||
    (value.revision as number) < 1 ||
    typeof value.created_at !== 'string' ||
    typeof value.updated_at !== 'string'
  )
    return invalidResponse();
  return { ...value, tags: tagLabelsFrom(value.tags) } as Entry;
}

export async function listEntries(
  cursor?: string,
  signal?: AbortSignal,
  tagId?: string,
): Promise<{ items: Entry[]; next_cursor: string | null }> {
  const query = new URLSearchParams({ limit: '20' });
  if (cursor) query.set('cursor', cursor);
  if (tagId) query.set('tag_id', tagId);
  const value = await request(`/entries?${query}`, { signal });
  if (
    !isRecord(value) ||
    !Array.isArray(value.items) ||
    !(value.next_cursor === null || typeof value.next_cursor === 'string')
  )
    return invalidResponse();
  return { items: value.items.map(entryFrom), next_cursor: value.next_cursor };
}

export async function getEntry(id: string): Promise<Entry> {
  return entryFrom(await request(`/entries/${encodeURIComponent(id)}`));
}

export async function createEntry(
  input: CreateInput,
  csrfToken: string,
): Promise<Entry> {
  return entryFrom(
    await request('/entries', { method: 'POST', body: input, csrfToken }),
  );
}

export async function updateEntry(
  id: string,
  input: EntryInput & { expected_revision: number },
  csrfToken: string,
): Promise<Entry> {
  return entryFrom(
    await request(`/entries/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: input,
      csrfToken,
    }),
  );
}

export async function deleteEntry(
  entry: Entry,
  csrfToken: string,
): Promise<void> {
  await request(
    `/entries/${encodeURIComponent(entry.id)}?expected_revision=${entry.revision}`,
    { method: 'DELETE', csrfToken },
  );
}

export async function listRevisions(
  id: string,
  before?: number,
  signal?: AbortSignal,
): Promise<{ items: EntryRevision[]; next_cursor: number | null }> {
  const query = new URLSearchParams({ limit: '20' });
  if (before !== undefined) query.set('before_revision', String(before));
  const value = await request(
    `/entries/${encodeURIComponent(id)}/revisions?${query}`,
    { signal },
  );
  if (
    !isRecord(value) ||
    !Array.isArray(value.items) ||
    !(value.next_cursor === null || Number.isInteger(value.next_cursor))
  )
    return invalidResponse();
  const items = value.items.map((item: unknown) => {
    if (
      !isRecord(item) ||
      !Number.isInteger(item.revision) ||
      typeof item.content_md !== 'string' ||
      typeof item.entry_date !== 'string' ||
      typeof item.changed_at !== 'string' ||
      typeof item.editor_id !== 'string'
    )
      return invalidResponse();
    return { ...item, tags: tagLabelsFrom(item.tags) } as EntryRevision;
  });
  return { items, next_cursor: value.next_cursor as number | null };
}
