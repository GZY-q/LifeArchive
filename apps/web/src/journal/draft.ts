import type { CreateInput, Entry, EntryInput } from '../api/journal';

export type Draft = EntryInput & {
  original: Entry | null;
  pendingCreate: CreateInput | null;
};

export function todayIn(timezone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const part = (name: string) =>
    parts.find((item) => item.type === name)!.value;
  return `${part('year').padStart(4, '0')}-${part('month')}-${part('day')}`;
}

export function emptyDraft(timezone: string): Draft {
  return {
    content_md: '',
    entry_date: todayIn(timezone),
    tag_ids: [],
    original: null,
    pendingCreate: null,
  };
}

export function hasUnsavedDraft(draft: Draft | null): boolean {
  if (!draft) return false;
  if (draft.pendingCreate) return true;
  if (!draft.original)
    return draft.content_md.length > 0 || draft.tag_ids.length > 0;
  return (
    draft.content_md !== draft.original.content_md ||
    draft.entry_date !== draft.original.entry_date ||
    [...draft.tag_ids].sort().join(',') !==
      draft.original.tags
        .map((tag) => tag.id)
        .sort()
        .join(',')
  );
}
