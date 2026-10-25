import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { App } from '../App';
import { json, mockApi, sampleEntry, session } from '../test/api-fixtures';

type Handler = Parameters<typeof mockApi>[0];
const previous = { ...sampleEntry, entry_date: '2020-02-29' };
const previousPage = (items = [previous], next_cursor: string | null = null) =>
  json({ date: '2024-02-29', entries: { items, next_cursor } });

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
    if (url.pathname === '/api/v1/on-this-day')
      return json({
        date: url.searchParams.get('date'),
        entries: { items: [], next_cursor: null },
      });
    return undefined;
  });
}

async function openCalendar(date = '2024-02-29') {
  await screen.findByLabelText('日记内容');
  await userEvent.click(screen.getByRole('button', { name: '日历' }));
  selectDate(date);
  return screen.getByRole('region', { name: '往年这一天' });
}

function selectDate(date: string) {
  fireEvent.change(screen.getByLabelText('跳转日期'), {
    target: { value: date },
  });
}

async function expand() {
  await userEvent.click(screen.getByRole('button', { name: '展开往年这一天' }));
}

async function logIn() {
  fireEvent.change(await screen.findByLabelText('用户名'), {
    target: { value: 'owner' },
  });
  fireEvent.change(screen.getByLabelText('密码'), {
    target: { value: 'test-password' },
  });
  await userEvent.click(screen.getByRole('button', { name: '登录' }));
}

describe('private on-this-day browsing', () => {
  it('loads only when expanded, keeps the selected date and displays full dates and untouched Markdown', async () => {
    const raw = '# 以前的闰日\n\n<img src=x onerror=unsafe()>  \n';
    const fetchMock = setupApi((path) =>
      path.startsWith('/api/v1/on-this-day')
        ? previousPage([{ ...previous, content_md: raw }])
        : undefined,
    );
    render(<App />);
    const region = await openCalendar();
    expect(
      fetchMock.mock.calls.some(([path]) => path.includes('/on-this-day')),
    ).toBe(false);
    expect(within(region).getByRole('button')).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    await expand();
    await within(region).findByRole('article');
    expect(within(region).getByText('2020-02-29')).toHaveAttribute(
      'dateTime',
      '2020-02-29',
    );
    expect(
      region.querySelector('article.on-this-day-entry pre')!.textContent,
    ).toBe(raw);
    expect(region.querySelector('img')).toBeNull();
    expect(
      fetchMock.mock.calls
        .filter(([path]) => path.includes('/on-this-day'))
        .map(([path]) => path),
    ).toEqual(['/api/v1/on-this-day?date=2024-02-29&limit=20']);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('uses the owner local date on the first expansion rather than UTC or entry creation time', async () => {
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
    await screen.findByLabelText('日记内容');
    await userEvent.click(screen.getByRole('button', { name: '日历' }));
    expect(screen.getByLabelText('跳转日期')).toHaveValue('2025-12-31');
    await expand();
    await screen.findByText('往年这一天还没有日记。');
    expect(
      fetchMock.mock.calls.some(
        ([path]) => path === '/api/v1/on-this-day?date=2025-12-31&limit=20',
      ),
    ).toBe(true);
  });

  it('retries first and later pages with the same reference date and cursor without losing earlier results', async () => {
    const paths: string[] = [];
    let firstAttempts = 0;
    let pageAttempts = 0;
    setupApi((path) => {
      if (!path.includes('/on-this-day')) return undefined;
      paths.push(path);
      if (!path.includes('cursor='))
        return ++firstAttempts === 1
          ? json({}, 503)
          : previousPage([previous], 'next');
      return ++pageAttempts === 1
        ? json({}, 503)
        : previousPage([
            previous,
            {
              ...previous,
              id: 'older',
              entry_date: '2016-02-29',
              content_md: '更早的闰日',
            },
          ]);
    });
    render(<App />);
    const region = await openCalendar();
    await expand();
    await userEvent.click(
      await screen.findByRole('button', { name: '重试读取往年日记' }),
    );
    await userEvent.click(
      await screen.findByRole('button', { name: '加载往年更多日记' }),
    );
    await screen.findByRole('button', { name: '重试读取往年日记' });
    expect(within(region).getAllByRole('article')).toHaveLength(1);
    await userEvent.click(
      screen.getByRole('button', { name: '重试读取往年日记' }),
    );
    await within(region).findByText('更早的闰日');
    expect(within(region).getAllByRole('article')).toHaveLength(2);
    expect(paths).toEqual([
      '/api/v1/on-this-day?date=2024-02-29&limit=20',
      '/api/v1/on-this-day?date=2024-02-29&limit=20',
      '/api/v1/on-this-day?date=2024-02-29&limit=20&cursor=next',
      '/api/v1/on-this-day?date=2024-02-29&limit=20&cursor=next',
    ]);
  });

  it.each(['first', 'next'])(
    'cancels a late %s page when the selected date changes while remaining expanded',
    async (stage) => {
      let resolveOld: (response: Response) => void = () => {};
      let oldSignal: AbortSignal | null | undefined;
      setupApi((path, options) => {
        if (!path.startsWith('/api/v1/on-this-day?date=2024-02-29'))
          return undefined;
        if (stage === 'next' && !path.includes('cursor='))
          return previousPage([previous], 'next');
        oldSignal = options.signal;
        return new Promise<Response>((resolve) => {
          resolveOld = resolve;
        });
      });
      render(<App />);
      const region = await openCalendar();
      await expand();
      if (stage === 'next')
        await userEvent.click(
          await screen.findByRole('button', { name: '加载往年更多日记' }),
        );
      selectDate('2024-02-28');
      expect(oldSignal?.aborted).toBe(true);
      await within(region).findByText('往年这一天还没有日记。');
      expect(
        within(region).getByRole('button', { name: '收起往年这一天' }),
      ).toHaveAttribute('aria-expanded', 'true');
      await act(async () =>
        resolveOld(
          previousPage([{ ...previous, content_md: '旧日期不得回流' }]),
        ),
      );
      expect(within(region).queryByRole('article')).not.toBeInTheDocument();
      expect(document.body.textContent).not.toContain('旧日期不得回流');
    },
  );

  it('refreshes an expanded region from the first page and cancels its outstanding pagination', async () => {
    let firstPages = 0;
    let resolvePage: (response: Response) => void = () => {};
    let pageSignal: AbortSignal | null | undefined;
    setupApi((path, options) => {
      if (!path.includes('/on-this-day')) return undefined;
      if (!path.includes('cursor='))
        return ++firstPages === 1
          ? previousPage([previous], 'next')
          : previousPage([]);
      pageSignal = options.signal;
      return new Promise<Response>((resolve) => {
        resolvePage = resolve;
      });
    });
    render(<App />);
    const region = await openCalendar();
    await expand();
    await userEvent.click(
      await screen.findByRole('button', { name: '加载往年更多日记' }),
    );
    await userEvent.click(screen.getByRole('button', { name: '刷新日历' }));
    expect(pageSignal?.aborted).toBe(true);
    await within(region).findByText('往年这一天还没有日记。');
    await act(async () =>
      resolvePage(previousPage([{ ...previous, content_md: '刷新前旧分页' }])),
    );
    expect(within(region).queryByRole('article')).not.toBeInTheDocument();
    expect(firstPages).toBe(2);
  });

  it('cancels reads on collapse and navigation, reloads after reopening, and keeps the unsaved journal draft', async () => {
    const signals: (AbortSignal | null | undefined)[] = [];
    const resolvers: ((response: Response) => void)[] = [];
    setupApi((path, options) => {
      if (!path.includes('/on-this-day')) return undefined;
      signals.push(options.signal);
      return new Promise<Response>((resolve) => {
        resolvers.push(resolve);
      });
    });
    render(<App />);
    const editor = await screen.findByLabelText('日记内容');
    fireEvent.change(editor, { target: { value: '# 未保存草稿  \n' } });
    fireEvent.change(screen.getByLabelText('日记日期'), {
      target: { value: '2001-02-03' },
    });
    await openCalendar();
    await expand();
    await userEvent.click(
      screen.getByRole('button', { name: '收起往年这一天' }),
    );
    expect(signals[0]?.aborted).toBe(true);
    await expand();
    expect(signals).toHaveLength(2);
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(signals[1]?.aborted).toBe(true);
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(editor).toHaveValue('# 未保存草稿  \n');
    expect(screen.getByLabelText('日记日期')).toHaveValue('2001-02-03');
    await act(async () => {
      for (const resolve of resolvers) resolve(previousPage());
    });
    const region = await openCalendar();
    expect(
      within(region).getByRole('button', { name: '展开往年这一天' }),
    ).toHaveAttribute('aria-expanded', 'false');
    expect(within(region).queryByRole('article')).not.toBeInTheDocument();
    expect(signals).toHaveLength(2);
  });

  it.each(['first', 'next'])(
    'removes all private DOM on a %s page 401 and restores the same-owner draft after login',
    async (stage) => {
      setupApi((path) => {
        if (!path.includes('/on-this-day')) return undefined;
        if (stage === 'next' && !path.includes('cursor='))
          return previousPage([previous], 'next');
        return json({}, 401);
      });
      render(<App />);
      fireEvent.change(await screen.findByLabelText('日记内容'), {
        target: { value: '登录后继续的草稿' },
      });
      await openCalendar();
      await expand();
      if (stage === 'next')
        await userEvent.click(
          await screen.findByRole('button', { name: '加载往年更多日记' }),
        );
      await screen.findByLabelText('密码');
      expect(
        document.querySelector(
          'textarea, .calendar-workspace, .on-this-day-entry',
        ),
      ).toBeNull();
      expect(document.body.textContent).not.toContain('登录后继续的草稿');
      await logIn();
      expect(
        await screen.findByRole('button', { name: '展开往年这一天' }),
      ).toHaveAttribute('aria-expanded', 'false');
      await userEvent.click(screen.getByRole('button', { name: '日记' }));
      expect(screen.getByLabelText('日记内容')).toHaveValue('登录后继续的草稿');
    },
  );

  it('clears earlier results and expansion on explicit logout', async () => {
    setupApi((path) => {
      if (path === '/api/v1/auth/logout')
        return new Response(null, { status: 204 });
      if (path.includes('/on-this-day')) return previousPage();
      return undefined;
    });
    render(<App />);
    const region = await openCalendar();
    await expand();
    await within(region).findByRole('article');
    await userEvent.click(screen.getByRole('button', { name: '退出登录' }));
    await screen.findByLabelText('密码');
    expect(document.querySelector('.on-this-day-entry')).toBeNull();
    await logIn();
    const reopened = await openCalendar();
    expect(
      within(reopened).getByRole('button', { name: '展开往年这一天' }),
    ).toHaveAttribute('aria-expanded', 'false');
    expect(within(reopened).queryByRole('article')).not.toBeInTheDocument();
  });
});
