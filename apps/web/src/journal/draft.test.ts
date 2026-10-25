import { describe, expect, it, vi } from 'vitest';

import { sampleEntry } from '../test/api-fixtures';
import { emptyDraft, hasUnsavedDraft, todayIn } from './draft';

describe('journal date', () => {
  it('treats tag-only edits as unsaved and compares labels as a set', () => {
    const draft = emptyDraft('Asia/Shanghai');
    expect(hasUnsavedDraft({ ...draft, tag_ids: ['a'] })).toBe(true);
    const original = {
      ...sampleEntry,
      tags: [
        { id: 'a', name: '生活' },
        { id: 'b', name: '阅读' },
      ],
    };
    const editing = {
      ...draft,
      original,
      content_md: original.content_md,
      entry_date: original.entry_date,
      tag_ids: ['b', 'a'],
    };
    expect(hasUnsavedDraft(editing)).toBe(false);
    expect(hasUnsavedDraft({ ...editing, tag_ids: [] })).toBe(true);
  });
  it('uses the owner timezone, independent of the browser timezone and UTC day', () => {
    vi.setSystemTime(new Date('2026-01-01T01:30:00Z'));
    expect(todayIn('Asia/Shanghai')).toBe('2026-01-01');
    expect(todayIn('Pacific/Honolulu')).toBe('2025-12-31');
  });
});
