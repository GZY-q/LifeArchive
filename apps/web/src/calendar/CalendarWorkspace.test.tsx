import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { App } from '../App';
import {
  json,
  mockApi,
  requestBody,
  sampleEntry,
  session,
} from '../test/api-fixtures';

type Handler = Parameters<typeof mockApi>[0];

function setupApi(handler: Handler = () => undefined) {
  return mockApi((path, options) => {
    const response = handler(path, options);
    if (response !== undefined) return response;
    const url = new URL(path, 'http://localhost');
    if (url.pathname === '/api/v1/calendar')
      return json({
        year: Number(url.searchParams.get('year')),
        month: Number(url.searchParams.get('month')),
        days: [],
      });
    if (url.pathname.startsWith('/api/v1/days/'))
      return json({
        date: url.pathname.split('/').at(-1),
        entries: { items: [], next_cursor: null },
      });
    return undefined;
  });
}

async function openCalendar() {
  await screen.findByLabelText('日记内容');
  await userEvent.click(screen.getByRole('button', { name: '日历' }));
  return screen.findByLabelText('跳转日期');
}

function selectDate(date: string) {
  fireEvent.change(screen.getByLabelText('跳转日期'), {
    target: { value: date },
  });
}

describe('private calendar browsing', () => {
  it('defaults to the owner timezone and keeps unsaved Markdown and date when returning to the journal', async () => {
    vi.setSystemTime(new Date('2026-01-01T01:30:00Z'));
    const fetchMock = setupApi((path) =>
      path === '/api/v1/auth/me'
        ? json({
            ...session,
            user: { ...session.user, timezone: 'Pacific/Honolulu' },
          })
        : undefined,
    );
    render(<App />);
    const editor = await screen.findByLabelText('日记内容');
    fireEvent.change(editor, {
      target: { value: '# 尚未保存\n\n保留尾空格。  \n' },
    });
    fireEvent.change(screen.getByLabelText('日记日期'), {
      target: { value: '2001-02-03' },
    });
    expect(await openCalendar()).toHaveValue('2025-12-31');
    expect(editor).not.toBeVisible();
    await screen.findByRole('button', { name: '2025-12-31，0 篇日记' });
    expect(
      fetchMock.mock.calls.some(
        ([path]) => path === '/api/v1/calendar?year=2025&month=12',
      ),
    ).toBe(true);
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(editor).toBeVisible();
    expect(editor).toHaveValue('# 尚未保存\n\n保留尾空格。  \n');
    expect(screen.getByLabelText('日记日期')).toHaveValue('2001-02-03');
    expect(
      fetchMock.mock.calls.every(
        ([, options]) => (options.method ?? 'GET') === 'GET',
      ),
    ).toBe(true);
  });

  it('retains an uncertain creation body and UUID across calendar navigation', async () => {
    const posts: Record<string, unknown>[] = [];
    setupApi((path, options) => {
      if (path === '/api/v1/entries' && options.method === 'POST') {
        posts.push(requestBody(options));
        return posts.length === 1
          ? Promise.reject(new TypeError('response lost'))
          : json(sampleEntry, 200);
      }
      return undefined;
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '只创建一次' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByText(/保存结果尚未确认/);
    await openCalendar();
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('日记已保存。');
    expect(posts).toHaveLength(2);
    expect(posts[1]).toEqual(posts[0]);
  });

  it('blocks navigation during writes and preserves the conflict decision when browsing the calendar', async () => {
    let rejectWrite: (response: Response) => void = () => {};
    mockApi(
      (path, options) => {
        if (options.method === 'PATCH')
          return new Promise<Response>((resolve) => {
            rejectWrite = resolve;
          });
        if (path.startsWith('/api/v1/calendar'))
          return json({ year: 2026, month: 10, days: [] });
        if (path.startsWith('/api/v1/days'))
          return json({
            date: '2026-10-25',
            entries: { items: [], next_cursor: null },
          });
        return undefined;
      },
      [sampleEntry],
    );
    vi.setSystemTime(new Date('2026-10-25T01:30:00Z'));
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: '编辑' }));
    fireEvent.change(screen.getByLabelText('日记内容'), {
      target: { value: '等待处理的冲突草稿' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    expect(screen.getByRole('button', { name: '日历' })).toBeDisabled();
    await act(async () =>
      rejectWrite(json({ detail: { code: 'revision_conflict' } }, 409)),
    );
    await screen.findByText(/这篇日记已有新的版本/);
    await openCalendar();
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toHaveValue('等待处理的冲突草稿');
    expect(screen.getByRole('button', { name: '保存修改' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '读取最新版本' })).toBeEnabled();
  });

  it('ignores a late month response after navigating to another month', async () => {
    vi.setSystemTime(new Date('2024-01-31T01:30:00Z'));
    let oldMonth: (response: Response) => void = () => {};
    setupApi((path) => {
      if (path === '/api/v1/calendar?year=2024&month=1')
        return new Promise<Response>((resolve) => {
          oldMonth = resolve;
        });
      if (path === '/api/v1/calendar?year=2024&month=2')
        return json({
          year: 2024,
          month: 2,
          days: [{ date: '2024-02-29', entry_count: 2 }],
        });
      return undefined;
    });
    render(<App />);
    await openCalendar();
    await userEvent.click(screen.getByRole('button', { name: '下一月' }));
    await screen.findByRole('button', { name: '2024-02-29，2 篇日记' });
    await act(async () =>
      oldMonth(
        json({
          year: 2024,
          month: 1,
          days: [{ date: '2024-01-31', entry_count: 99 }],
        }),
      ),
    );
    expect(screen.getByLabelText('跳转日期')).toHaveValue('2024-02-29');
    expect(
      screen.getByRole('button', { name: '2024-02-29，2 篇日记' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /2024-01-31/ }),
    ).not.toBeInTheDocument();
  });

  it('bounds month navigation and renders leap-day selection', async () => {
    setupApi();
    render(<App />);
    await openCalendar();
    selectDate('0001-01-01');
    expect(screen.getByRole('button', { name: '上一月' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '下一月' })).toBeEnabled();
    selectDate('9999-12-31');
    expect(screen.getByRole('button', { name: '下一月' })).toBeDisabled();
    selectDate('2024-02-29');
    await userEvent.click(
      await screen.findByRole('button', { name: '2024-02-29，0 篇日记' }),
    );
    expect(
      screen.getByRole('region', { name: '2024-02-29 的日记' }),
    ).toBeInTheDocument();
    selectDate('2023-02-01');
    expect(
      screen.queryByRole('button', { name: /2023-02-29/ }),
    ).not.toBeInTheDocument();
  });

  it('retries a failed month without pretending that unknown counts are zero', async () => {
    vi.setSystemTime(new Date('2024-02-29T01:30:00Z'));
    let attempts = 0;
    setupApi((path) =>
      path.startsWith('/api/v1/calendar')
        ? ++attempts === 1
          ? json({}, 503)
          : json({
              year: 2024,
              month: 2,
              days: [{ date: '2024-02-29', entry_count: 3 }],
            })
        : undefined,
    );
    render(<App />);
    await openCalendar();
    await screen.findByRole('button', { name: '重试读取日历' });
    expect(
      screen.queryByRole('button', { name: '2024-02-29，0 篇日记' }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '重试读取日历' }));
    await screen.findByRole('button', { name: '2024-02-29，3 篇日记' });
  });

  it('paginates the selected day, retries a failed next page, and displays raw Markdown safely', async () => {
    vi.setSystemTime(new Date('2024-02-29T01:30:00Z'));
    const raw = '<img src=x onerror=private()>\n中文尾空格。  \n';
    const first = { ...sampleEntry, content_md: raw, entry_date: '2024-02-29' };
    let moreAttempts = 0;
    const fetchMock = setupApi((path) => {
      if (!path.startsWith('/api/v1/days/2024-02-29?')) return undefined;
      if (!path.includes('cursor='))
        return json({
          date: first.entry_date,
          entries: { items: [first], next_cursor: 'opaque+/=' },
        });
      return ++moreAttempts === 1
        ? json({}, 503)
        : json({
            date: first.entry_date,
            entries: {
              items: [
                first,
                { ...first, id: 'second-entry', content_md: '更早的一条' },
              ],
              next_cursor: null,
            },
          });
    });
    render(<App />);
    await openCalendar();
    const region = await screen.findByRole('region', {
      name: '2024-02-29 的日记',
    });
    await within(region).findByRole('article');
    expect(region.querySelector('pre')!.textContent).toBe(raw);
    expect(region.querySelector('img')).toBeNull();
    await userEvent.click(
      within(region).getByRole('button', { name: '加载这一天的更多日记' }),
    );
    await within(region).findByRole('alert');
    expect(within(region).getAllByRole('article')).toHaveLength(1);
    await userEvent.click(
      within(region).getByRole('button', { name: '加载这一天的更多日记' }),
    );
    await within(region).findByText('更早的一条');
    expect(within(region).getAllByRole('article')).toHaveLength(2);
    expect(
      fetchMock.mock.calls.some(
        ([path]) =>
          new URL(path, 'http://localhost').searchParams.get('cursor') ===
          'opaque+/=',
      ),
    ).toBe(true);
  });

  it('cancels a previous day page when another day is selected', async () => {
    vi.setSystemTime(new Date('2024-02-29T01:30:00Z'));
    let oldPage: (response: Response) => void = () => {};
    setupApi((path) => {
      if (path.startsWith('/api/v1/days/2024-02-29?')) {
        if (path.includes('cursor='))
          return new Promise<Response>((resolve) => {
            oldPage = resolve;
          });
        return json({
          date: '2024-02-29',
          entries: {
            items: [{ ...sampleEntry, entry_date: '2024-02-29' }],
            next_cursor: 'next-page',
          },
        });
      }
      return undefined;
    });
    render(<App />);
    await openCalendar();
    await userEvent.click(
      await screen.findByRole('button', { name: '加载这一天的更多日记' }),
    );
    selectDate('2024-02-28');
    await screen.findByText('这一天还没有日记。');
    await act(async () =>
      oldPage(
        json({
          date: '2024-02-29',
          entries: {
            items: [
              {
                ...sampleEntry,
                entry_date: '2024-02-29',
                content_md: '不应显示的旧分页',
              },
            ],
            next_cursor: null,
          },
        }),
      ),
    );
    const region = screen.getByRole('region', { name: '2024-02-28 的日记' });
    expect(within(region).queryByRole('article')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('不应显示的旧分页');
  });

  it('retries an unavailable day and refreshes both month and day after a changed record', async () => {
    vi.setSystemTime(new Date('2024-02-29T01:30:00Z'));
    let dayAttempts = 0;
    let deleted = false;
    setupApi((path) => {
      if (path.startsWith('/api/v1/calendar'))
        return json({
          year: 2024,
          month: 2,
          days: deleted ? [] : [{ date: '2024-02-29', entry_count: 1 }],
        });
      if (path.startsWith('/api/v1/days/2024-02-29?')) {
        if (++dayAttempts === 1) return json({}, 503);
        return json({
          date: '2024-02-29',
          entries: {
            items: deleted
              ? []
              : [{ ...sampleEntry, entry_date: '2024-02-29' }],
            next_cursor: null,
          },
        });
      }
      return undefined;
    });
    render(<App />);
    await openCalendar();
    await userEvent.click(
      await screen.findByRole('button', { name: '重试读取这一天' }),
    );
    await screen.findByRole('article');
    deleted = true;
    await userEvent.click(screen.getByRole('button', { name: '刷新日历' }));
    await screen.findByRole('button', { name: '2024-02-29，0 篇日记' });
    await screen.findByText('这一天还没有日记。');
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });

  it('removes the calendar and hidden journal DOM on 401 while retaining the same-owner draft in memory', async () => {
    let dayAttempts = 0;
    setupApi((path) =>
      path.startsWith('/api/v1/days/') && ++dayAttempts === 1
        ? json({}, 401)
        : undefined,
    );
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '需要重新登录的草稿' },
    });
    await userEvent.click(screen.getByRole('button', { name: '日历' }));
    await screen.findByLabelText('密码');
    expect(
      document.querySelector('textarea, .calendar-workspace, .day-detail'),
    ).toBeNull();
    expect(document.body.textContent).not.toContain('需要重新登录的草稿');
    expect(
      screen.queryByRole('navigation', { name: '主导航' }),
    ).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('用户名'), {
      target: { value: 'owner' },
    });
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'test-password' },
    });
    await userEvent.click(screen.getByRole('button', { name: '登录' }));
    await screen.findByRole('button', { name: '日记' });
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toHaveValue('需要重新登录的草稿');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
