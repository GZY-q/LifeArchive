import { useEffect, useState } from 'react';

import { getCalendar } from '../api/calendar';
import type { CalendarMonth } from '../api/calendar';
import { errorMessage, isUnauthorized } from '../api/client';
import { todayIn } from '../journal/draft';
import {
  adjacentMonth,
  daysInMonth,
  firstWeekday,
  formatCalendarDate,
  parseCalendarDate,
} from './dates';
import { DayEntries } from './DayEntries';

type Props = {
  date: string;
  timezone: string;
  disabled: boolean;
  onDate: (date: string) => void;
  onExpired: () => void;
};
type MonthResult = { key: string; data?: CalendarMonth; error?: string };

export function CalendarWorkspace({
  date,
  timezone,
  disabled,
  onDate,
  onExpired,
}: Props) {
  const selected = parseCalendarDate(date)!;
  const { year, month } = selected;
  const [refresh, setRefresh] = useState(0);
  const [result, setResult] = useState<MonthResult | null>(null);
  const key = `${year}-${month}:${refresh}`;
  const current = result?.key === key ? result : null;
  const today = todayIn(timezone);
  const previous = adjacentMonth(selected, -1);
  const next = adjacentMonth(selected, 1);
  const counts = new Map(
    current?.data?.days.map((item) => [item.date, item.entry_count]),
  );

  useEffect(() => {
    const controller = new AbortController();
    void getCalendar(year, month, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setResult({ key, data });
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(cause)) onExpired();
        else setResult({ key, error: errorMessage(cause) });
      });
    return () => controller.abort();
  }, [year, month, key, onExpired]);

  return (
    <div className="calendar-workspace">
      <section className="calendar-panel paper-card" aria-label="月历">
        <div className="section-heading">
          <div>
            <p className="eyebrow">ONE DAY AT A TIME</p>
            <h2>
              {year} 年 {month} 月
            </h2>
          </div>
          <button
            className="text-button"
            type="button"
            disabled={disabled}
            onClick={() => {
              onDate(today);
              setRefresh((value) => value + 1);
            }}
          >
            回到今天
          </button>
        </div>
        <div className="calendar-controls">
          <div className="month-navigation">
            <button
              className="secondary-button"
              type="button"
              disabled={disabled || !previous}
              onClick={() => previous && onDate(previous)}
            >
              上一月
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={disabled || !next}
              onClick={() => next && onDate(next)}
            >
              下一月
            </button>
          </div>
          <label htmlFor="calendar-date">
            跳转日期
            <input
              id="calendar-date"
              type="date"
              min="0001-01-01"
              max="9999-12-31"
              value={date}
              disabled={disabled}
              onChange={(event) => {
                if (parseCalendarDate(event.target.value))
                  onDate(event.target.value);
              }}
            />
          </label>
        </div>
        {!current && (
          <p className="calendar-status" role="status">
            正在读取日记数量…
          </p>
        )}
        {current?.error && (
          <p className="error-message" role="alert">
            日历读取失败。{current.error}
          </p>
        )}
        {current?.data && (
          <p className="calendar-status small-note">
            {current.data.days.reduce(
              (total, day) => total + day.entry_count,
              0,
            )}{' '}
            篇日记 · 按日记日期归档
          </p>
        )}
        <div className="weekdays" aria-hidden="true">
          {['一', '二', '三', '四', '五', '六', '日'].map((day) => (
            <span key={day}>{day}</span>
          ))}
        </div>
        <div
          className="calendar-grid"
          role="group"
          aria-label={`${year} 年 ${month} 月的日期`}
        >
          {Array.from({ length: firstWeekday(year, month) }, (_, index) => (
            <span key={`blank-${index}`} aria-hidden="true" />
          ))}
          {Array.from({ length: daysInMonth(year, month) }, (_, index) => {
            const day = index + 1;
            const value = formatCalendarDate({ year, month, day });
            const count = counts.get(value) ?? 0;
            const description = current?.data
              ? `${count} 篇日记`
              : current?.error
                ? '日记数量未能加载'
                : '正在读取日记数量';
            return (
              <button
                type="button"
                className="calendar-day"
                key={value}
                disabled={disabled}
                aria-label={`${value}，${description}`}
                aria-pressed={date === value}
                aria-current={today === value ? 'date' : undefined}
                onClick={() => onDate(value)}
              >
                <span>{day}</span>
                <span className="day-count" aria-hidden="true">
                  {current?.data && count > 0 ? `${count} 篇` : '\u00a0'}
                </span>
              </button>
            );
          })}
        </div>
        <button
          className="text-button calendar-refresh"
          type="button"
          disabled={disabled || !current}
          onClick={() => setRefresh((value) => value + 1)}
        >
          {current?.error ? '重试读取日历' : '刷新日历'}
        </button>
      </section>
      <DayEntries
        key={`${date}:${refresh}`}
        date={date}
        disabled={disabled}
        onExpired={onExpired}
      />
    </div>
  );
}
