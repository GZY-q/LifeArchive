import { describe, expect, it } from 'vitest';

import {
  adjacentMonth,
  daysInMonth,
  firstWeekday,
  parseCalendarDate,
} from './dates';

describe('archive calendar dates', () => {
  it.each([
    [1900, 28],
    [2000, 29],
    [2024, 29],
    [2100, 28],
  ])('uses Gregorian leap-year rules for February %i', (year, length) => {
    expect(daysInMonth(year, 2)).toBe(length);
    expect(parseCalendarDate(`${year}-02-29`) !== null).toBe(length === 29);
  });

  it.each([
    '0000-01-01',
    '10000-01-01',
    '2026-13-01',
    '2026-04-31',
    '2026-1-01',
  ])('rejects invalid archive date %s', (date) => {
    expect(parseCalendarDate(date)).toBeNull();
  });

  it('keeps early years and known weekdays independent of JS Date conversions', () => {
    expect(parseCalendarDate('0001-01-01')).toEqual({
      year: 1,
      month: 1,
      day: 1,
    });
    expect(parseCalendarDate('0099-12-31')).toEqual({
      year: 99,
      month: 12,
      day: 31,
    });
    expect(firstWeekday(1, 1)).toBe(0); // Monday
    expect(firstWeekday(2000, 1)).toBe(5); // Saturday
    expect(firstWeekday(2024, 2)).toBe(3); // Thursday
  });

  it('moves across years and clamps the selected day without overflowing the supported range', () => {
    expect(adjacentMonth({ year: 2024, month: 1, day: 31 }, 1)).toBe(
      '2024-02-29',
    );
    expect(adjacentMonth({ year: 2025, month: 1, day: 31 }, 1)).toBe(
      '2025-02-28',
    );
    expect(adjacentMonth({ year: 2024, month: 12, day: 31 }, 1)).toBe(
      '2025-01-31',
    );
    expect(adjacentMonth({ year: 1, month: 1, day: 1 }, -1)).toBeNull();
    expect(adjacentMonth({ year: 9999, month: 12, day: 31 }, 1)).toBeNull();
  });
});
