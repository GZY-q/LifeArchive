import { describe, expect, it, vi } from 'vitest';

import { json, sampleEntry } from '../test/api-fixtures';
import { getOnThisDay } from './calendar';

const previous = { ...sampleEntry, entry_date: '2020-02-29' };
const page = (items: unknown[] = [previous], next_cursor: unknown = null) => ({
  date: '2024-02-29',
  entries: { items, next_cursor },
});

describe('on-this-day API boundary', () => {
  it('keeps the reference date and opaque cursor on each authenticated no-store read', async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(page()));
    vi.stubGlobal('fetch', fetchMock);
    const result = await getOnThisDay('2024-02-29', 'opaque+/=');
    expect(result).toEqual(page());
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/on-this-day?date=2024-02-29&limit=20&cursor=opaque%2B%2F%3D',
      expect.objectContaining({
        method: 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
      }),
    );
  });

  it.each([
    { ...page(), date: '2024-02-28' },
    page([{ ...previous, entry_date: '2024-02-29' }]),
    page([{ ...previous, entry_date: '2028-02-29' }]),
    page([{ ...previous, entry_date: '2020-02-28' }]),
    page([{ ...previous, entry_date: '2020-03-29' }]),
    page([{ ...previous, entry_date: '1900-02-29' }]),
    page([{ ...previous, entry_date: '0000-02-29' }]),
    page([{ ...previous, entry_date: '20200229' }]),
    page([{ ...previous, revision: 0 }]),
    page([], ''),
    page([], 'x'.repeat(2049)),
    page([], 12),
    { date: '2024-02-29', entries: { items: null, next_cursor: null } },
  ])('rejects malformed or out-of-scope results: %j', async (response) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(response)));
    await expect(getOnThisDay('2024-02-29')).rejects.toMatchObject({
      status: 0,
      code: 'invalid_response',
    });
  });

  it('accepts an empty year-one result and full dates through year 9999', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        json({ date: '0001-01-01', entries: { items: [], next_cursor: null } }),
      )
      .mockResolvedValueOnce(
        json({
          date: '9999-12-31',
          entries: {
            items: [{ ...previous, entry_date: '0001-12-31' }],
            next_cursor: null,
          },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);
    expect((await getOnThisDay('0001-01-01')).entries.items).toEqual([]);
    expect((await getOnThisDay('9999-12-31')).entries.items[0].entry_date).toBe(
      '0001-12-31',
    );
  });
});
