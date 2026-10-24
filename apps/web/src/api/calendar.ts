import { parseCalendarDate } from '../calendar/dates';
import { invalidResponse, isRecord, request } from './client';
import { entryFrom } from './journal';
import type { Entry } from './journal';

export type CalendarMonth = {
  year: number;
  month: number;
  days: { date: string; entry_count: number }[];
};
export type DayEntries = {
  date: string;
  entries: { items: Entry[]; next_cursor: string | null };
};

export async function getCalendar(
  year: number,
  month: number,
  signal?: AbortSignal,
): Promise<CalendarMonth> {
  const value = await request(
    `/calendar?${new URLSearchParams({ year: String(year), month: String(month) })}`,
    { signal },
  );
  if (
    !isRecord(value) ||
    value.year !== year ||
    value.month !== month ||
    !Array.isArray(value.days)
  )
    return invalidResponse();
  let previous = '';
  const days = value.days.map((item: unknown) => {
    if (
      !isRecord(item) ||
      typeof item.date !== 'string' ||
      !Number.isSafeInteger(item.entry_count) ||
      (item.entry_count as number) < 1
    )
      return invalidResponse();
    const date = parseCalendarDate(item.date);
    if (
      !date ||
      date.year !== year ||
      date.month !== month ||
      item.date <= previous
    )
      return invalidResponse();
    previous = item.date;
    return { date: item.date, entry_count: item.entry_count as number };
  });
  return { year, month, days };
}

export async function getDay(
  date: string,
  cursor?: string,
  signal?: AbortSignal,
): Promise<DayEntries> {
  const query = new URLSearchParams({ limit: '20' });
  if (cursor) query.set('cursor', cursor);
  const value = await request(`/days/${encodeURIComponent(date)}?${query}`, {
    signal,
  });
  if (
    !isRecord(value) ||
    value.date !== date ||
    !isRecord(value.entries) ||
    !Array.isArray(value.entries.items) ||
    !(
      value.entries.next_cursor === null ||
      typeof value.entries.next_cursor === 'string'
    )
  )
    return invalidResponse();
  const items = value.entries.items.map(entryFrom);
  if (items.some((item) => item.entry_date !== date)) return invalidResponse();
  return { date, entries: { items, next_cursor: value.entries.next_cursor } };
}
