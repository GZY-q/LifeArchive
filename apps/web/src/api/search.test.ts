import { describe, expect, it, vi } from 'vitest';

import { json, sampleEntry } from '../test/api-fixtures';
import { searchEntries } from './search';

const filters = { query: '私人中文 100%_\\/', date_from: null, date_to: null };

describe('private search API boundary', () => {
  it('sends literal text and pagination only in a no-store POST body with the current CSRF token', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(json({ items: [sampleEntry], next_cursor: null }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(
      searchEntries(filters, 'current-token', 'opaque+/='),
    ).resolves.toEqual({
      items: [sampleEntry],
      next_cursor: null,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search',
      expect.objectContaining({
        method: 'POST',
        cache: 'no-store',
        credentials: 'same-origin',
        headers: expect.objectContaining({
          'X-CSRF-Token': 'current-token',
          'X-LifeArchive-Request': '1',
        }),
        body: JSON.stringify({ ...filters, limit: 20, cursor: 'opaque+/=' }),
      }),
    );
  });

  it.each([
    { items: null, next_cursor: null },
    { items: [{ ...sampleEntry, revision: 0 }], next_cursor: null },
    { items: [], next_cursor: 12 },
    { items: [], next_cursor: '' },
    { items: [], next_cursor: 'x'.repeat(2049) },
  ])('rejects invalid result pages: %j', async (response) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(response)));
    await expect(searchEntries(filters, 'token')).rejects.toMatchObject({
      status: 0,
      code: 'invalid_response',
    });
  });
});
