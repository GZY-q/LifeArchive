import { invalidResponse, isRecord, request } from './client';

export type TagLabel = { id: string; name: string };
export type Tag = TagLabel & { created_at: string };

export function tagLabelsFrom(value: unknown): TagLabel[] {
  if (!Array.isArray(value)) return invalidResponse();
  return value.map((item: unknown) => {
    if (
      !isRecord(item) ||
      typeof item.id !== 'string' ||
      typeof item.name !== 'string'
    )
      return invalidResponse();
    return { id: item.id, name: item.name };
  });
}

function tagFrom(value: unknown): Tag {
  if (!isRecord(value) || typeof value.created_at !== 'string')
    return invalidResponse();
  return { ...tagLabelsFrom([value])[0], created_at: value.created_at };
}

export async function listTags(signal?: AbortSignal): Promise<Tag[]> {
  const items: Tag[] = [];
  const seen = new Set<string>();
  let cursor: string | null = null;
  do {
    const query = new URLSearchParams({ limit: '200' });
    if (cursor) query.set('cursor', cursor);
    const value = await request(`/tags?${query}`, { signal });
    if (
      !isRecord(value) ||
      !Array.isArray(value.items) ||
      !(value.next_cursor === null || typeof value.next_cursor === 'string')
    )
      return invalidResponse();
    items.push(...value.items.map(tagFrom));
    cursor = value.next_cursor;
    if (cursor !== null) {
      if (seen.has(cursor)) return invalidResponse();
      seen.add(cursor);
    }
  } while (cursor !== null);
  return items.sort(
    (a, b) => a.name.localeCompare(b.name, 'zh-CN') || a.id.localeCompare(b.id),
  );
}

export async function createTag(name: string, csrfToken: string): Promise<Tag> {
  return tagFrom(
    await request('/tags', { method: 'POST', body: { name }, csrfToken }),
  );
}
