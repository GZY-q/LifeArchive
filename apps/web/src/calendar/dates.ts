export type CalendarDate = { year: number; month: number; day: number };

export function daysInMonth(year: number, month: number): number {
  if (
    !Number.isInteger(year) ||
    year < 1 ||
    year > 9999 ||
    !Number.isInteger(month) ||
    month < 1 ||
    month > 12
  ) {
    throw new RangeError('Calendar month out of range');
  }
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][
    month - 1
  ];
}

export function parseCalendarDate(value: string): CalendarDate | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  if (
    year < 1 ||
    year > 9999 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > daysInMonth(year, month)
  )
    return null;
  return { year, month, day };
}

export function formatCalendarDate({ year, month, day }: CalendarDate): string {
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

/** Gregorian arithmetic avoids the Date constructor's year 0–99 and UTC conversions. */
export function firstWeekday(year: number, month: number): number {
  daysInMonth(year, month);
  const previousYear = year - 1;
  let elapsed =
    365 * previousYear +
    Math.floor(previousYear / 4) -
    Math.floor(previousYear / 100) +
    Math.floor(previousYear / 400);
  for (let before = 1; before < month; before += 1)
    elapsed += daysInMonth(year, before);
  // 0001-01-01 is Monday; return a Monday-first column index.
  return elapsed % 7;
}

export function adjacentMonth(
  date: CalendarDate,
  offset: -1 | 1,
): string | null {
  const index = (date.year - 1) * 12 + date.month - 1 + offset;
  if (index < 0 || index >= 9999 * 12) return null;
  const year = Math.floor(index / 12) + 1;
  const month = (index % 12) + 1;
  return formatCalendarDate({
    year,
    month,
    day: Math.min(date.day, daysInMonth(year, month)),
  });
}
