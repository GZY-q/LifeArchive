import { describe, expect, it, vi } from 'vitest';

import { json, sampleEntry } from '../test/api-fixtures';
import { getCalendar, getDay } from './calendar';

describe('calendar response boundary', () => {
  it.each([
    { year: 2024, month: 3, days: [] },
    { year: 2024, month: 2, days: [{ date: '2024-03-01', entry_count: 1 }] },
    { year: 2024, month: 2, days: [{ date: '2024-02-30', entry_count: 1 }] },
    { year: 2024, month: 2, days: [{ date: '2024-02-01', entry_count: 0 }] },
    { year: 2024, month: 2, days: [{ date: '2024-02-01', entry_count: 1.5 }] },
    {
      year: 2024,
      month: 2,
      days: [
        { date: '2024-02-02', entry_count: 1 },
        { date: '2024-02-01', entry_count: 1 },
      ],
    },
  ])('rejects malformed or mismatched monthly data: %j', async (response) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(response)));
    await expect(getCalendar(2024, 2)).rejects.toMatchObject({
      status: 0,
      code: 'invalid_response',
    });
  });

  it('rejects entries assigned to another archive date instead of displaying them under the selected day', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        json({
          date: '2024-02-29',
          entries: { items: [sampleEntry], next_cursor: null },
        }),
      ),
    );
    await expect(getDay('2024-02-29')).rejects.toMatchObject({
      status: 0,
      code: 'invalid_response',
    });
  });
});
