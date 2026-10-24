import { describe, expect, it, vi } from 'vitest';

import { todayIn } from './draft';

describe('journal date', () => {
  it('uses the owner timezone, independent of the browser timezone and UTC day', () => {
    vi.setSystemTime(new Date('2026-01-01T01:30:00Z'));
    expect(todayIn('Asia/Shanghai')).toBe('2026-01-01');
    expect(todayIn('Pacific/Honolulu')).toBe('2025-12-31');
  });
});
