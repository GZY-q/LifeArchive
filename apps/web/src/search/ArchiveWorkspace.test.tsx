import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '../App';
import {
  json,
  mockApi,
  requestBody,
  sampleEntry,
  session,
} from '../test/api-fixtures';

async function openArchive() {
  await screen.findByLabelText('日记内容');
  await userEvent.click(screen.getByRole('button', { name: '归档' }));
  return screen.findByRole('region', { name: '归档搜索' });
}

function query(value: string) {
  fireEvent.change(screen.getByLabelText('关键词'), { target: { value } });
}

async function submit() {
  await userEvent.click(screen.getByRole('button', { name: '搜索日记' }));
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

describe('private archive search', () => {
  it('submits only on request, validates empty/date/long input locally, and supports date-only search', async () => {
    const bodies: Record<string, unknown>[] = [];
    mockApi((path, options) => {
      if (path !== '/api/v1/search') return undefined;
      bodies.push(requestBody(options));
      return json({ items: [], next_cursor: null });
    });
    render(<App />);
    await openArchive();
    await submit();
    expect(screen.getByRole('alert')).toHaveTextContent(
      '请输入关键词，或至少选择一个日记日期或标签。',
    );
    query('中文');
    expect(bodies).toHaveLength(0);
    fireEvent.change(screen.getByLabelText('开始日期'), {
      target: { value: '2024-03-01' },
    });
    fireEvent.change(screen.getByLabelText('结束日期'), {
      target: { value: '2024-02-29' },
    });
    await submit();
    expect(screen.getByRole('alert')).toHaveTextContent(
      '开始日期不能晚于结束日期。',
    );
    fireEvent.change(screen.getByLabelText('开始日期'), {
      target: { value: '' },
    });
    query('字'.repeat(201));
    await submit();
    expect(screen.getByRole('alert')).toHaveTextContent(
      '关键词最多 200 个字符',
    );
    expect(bodies).toHaveLength(0);
    query('  ');
    await submit();
    await screen.findByText('没有找到符合条件的日记。');
    expect(bodies).toEqual([
      {
        query: '',
        date_from: null,
        date_to: '2024-02-29',
        limit: 20,
        cursor: null,
      },
    ]);
  });

  it('keeps Chinese IME composition local and displays raw original Markdown without HTML interpretation', async () => {
    const raw = '<img src=x onerror=private()>\n# 中文原文  \n';
    const fetchMock = mockApi((path) =>
      path === '/api/v1/search'
        ? json({
            items: [{ ...sampleEntry, content_md: raw }],
            next_cursor: null,
          })
        : undefined,
    );
    render(<App />);
    const region = await openArchive();
    const input = screen.getByLabelText('关键词');
    fireEvent.compositionStart(input);
    query('  中文 100%_\\/  ');
    fireEvent.submit(input.closest('form')!);
    expect(
      fetchMock.mock.calls.filter(([path]) => path === '/api/v1/search'),
    ).toHaveLength(0);
    fireEvent.compositionEnd(input);
    await submit();
    await within(region).findByRole('article');
    expect(region.querySelector('article.archive-entry pre')!.textContent).toBe(
      raw,
    );
    expect(region.querySelector('img')).toBeNull();
    const [path, options] = fetchMock.mock.calls.find(
      ([path]) => path === '/api/v1/search',
    )!;
    expect(path).toBe('/api/v1/search');
    expect(requestBody(options)).toEqual({
      query: '中文 100%_\\/',
      date_from: null,
      date_to: null,
      limit: 20,
      cursor: null,
    });
    expect(options.headers).toMatchObject({
      'X-CSRF-Token': session.csrf_token,
    });
    expect(window.location.search).toBe('');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('paginates and retries with the submitted filters even when the form has been edited', async () => {
    const bodies: Record<string, unknown>[] = [];
    let pageAttempts = 0;
    mockApi((path, options) => {
      if (path !== '/api/v1/search') return undefined;
      const body = requestBody(options);
      bodies.push(body);
      if (!body.cursor)
        return json({ items: [sampleEntry], next_cursor: 'page-two' });
      return ++pageAttempts === 1
        ? json({}, 503)
        : json({
            items: [
              sampleEntry,
              { ...sampleEntry, id: 'older', content_md: '更早的结果' },
            ],
            next_cursor: null,
          });
    });
    render(<App />);
    const region = await openArchive();
    query('原始关键词');
    fireEvent.change(screen.getByLabelText('开始日期'), {
      target: { value: '2001-02-03' },
    });
    await submit();
    await within(region).findByRole('article');
    query('尚未提交的新词');
    fireEvent.change(screen.getByLabelText('开始日期'), {
      target: { value: '2025-01-01' },
    });
    expect(screen.getByText(/已提交条件/)).toHaveTextContent(
      '关键词「原始关键词」 · 2001-02-03 至 最新',
    );
    await userEvent.click(screen.getByRole('button', { name: '加载更多结果' }));
    await screen.findByRole('button', { name: '重试搜索' });
    expect(within(region).getAllByRole('article')).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: '重试搜索' }));
    await within(region).findByText('更早的结果');
    expect(within(region).getAllByRole('article')).toHaveLength(2);
    expect(bodies).toEqual([
      {
        query: '原始关键词',
        date_from: '2001-02-03',
        date_to: null,
        limit: 20,
        cursor: null,
      },
      {
        query: '原始关键词',
        date_from: '2001-02-03',
        date_to: null,
        limit: 20,
        cursor: 'page-two',
      },
      {
        query: '原始关键词',
        date_from: '2001-02-03',
        date_to: null,
        limit: 20,
        cursor: 'page-two',
      },
    ]);
  });

  it('retries a failed first page with the submitted query and the refreshed CSRF token', async () => {
    let checks = 0;
    const bodies: Record<string, unknown>[] = [];
    const tokens: unknown[] = [];
    mockApi((path, options) => {
      if (path === '/api/v1/auth/me')
        return json({
          ...session,
          csrf_token: ++checks === 1 ? 'old-token' : 'new-token',
        });
      if (path !== '/api/v1/search') return undefined;
      bodies.push(requestBody(options));
      tokens.push(new Headers(options.headers).get('X-CSRF-Token'));
      return bodies.length === 1
        ? json({}, 403)
        : json({ items: [sampleEntry], next_cursor: null });
    });
    render(<App />);
    await openArchive();
    query('原始关键词');
    await submit();
    await screen.findByRole('button', { name: '重试搜索' });
    query('未提交');
    await userEvent.click(screen.getByRole('button', { name: '重新验证登录' }));
    await userEvent.click(screen.getByRole('button', { name: '重试搜索' }));
    await screen.findByRole('article');
    expect(bodies[1]).toEqual(bodies[0]);
    expect(tokens).toEqual(['old-token', 'new-token']);
  });

  it('aborts and ignores a slow previous query when a new search finishes first', async () => {
    let resolveOld: (response: Response) => void = () => {};
    let oldSignal: AbortSignal | null | undefined;
    mockApi((path, options) => {
      if (path !== '/api/v1/search') return undefined;
      if (requestBody(options).query === '旧词') {
        oldSignal = options.signal;
        return new Promise<Response>((resolve) => {
          resolveOld = resolve;
        });
      }
      return json({
        items: [{ ...sampleEntry, content_md: '新搜索结果' }],
        next_cursor: null,
      });
    });
    render(<App />);
    await openArchive();
    query('旧词');
    await submit();
    query('新词');
    await submit();
    await screen.findByText('新搜索结果');
    expect(oldSignal?.aborted).toBe(true);
    await act(async () =>
      resolveOld(
        json({
          items: [{ ...sampleEntry, content_md: '旧请求不应出现' }],
          next_cursor: null,
        }),
      ),
    );
    expect(document.body.textContent).not.toContain('旧请求不应出现');
    expect(screen.getByText(/已提交条件/)).toHaveTextContent('关键词「新词」');
  });

  it('cancels an old next page when a new search replaces its filters', async () => {
    let resolvePage: (response: Response) => void = () => {};
    let pageSignal: AbortSignal | null | undefined;
    mockApi((path, options) => {
      if (path !== '/api/v1/search') return undefined;
      const body = requestBody(options);
      if (body.cursor) {
        pageSignal = options.signal;
        return new Promise<Response>((resolve) => {
          resolvePage = resolve;
        });
      }
      return json({
        items: body.query === '旧词' ? [sampleEntry] : [],
        next_cursor: body.query === '旧词' ? 'next' : null,
      });
    });
    render(<App />);
    await openArchive();
    query('旧词');
    await submit();
    await userEvent.click(
      await screen.findByRole('button', { name: '加载更多结果' }),
    );
    query('新词');
    await submit();
    await screen.findByText('没有找到符合条件的日记。');
    expect(pageSignal?.aborted).toBe(true);
    await act(async () =>
      resolvePage(
        json({
          items: [{ ...sampleEntry, id: 'old-page', content_md: '过期分页' }],
          next_cursor: null,
        }),
      ),
    );
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('过期分页');
  });

  it('keeps journal drafts and search inputs on navigation, cancels outstanding requests, and requires a fresh submit on return', async () => {
    let resolveSearch: (response: Response) => void = () => {};
    let searchSignal: AbortSignal | null | undefined;
    const fetchMock = mockApi((path, options) => {
      if (path !== '/api/v1/search') return undefined;
      searchSignal = options.signal;
      return new Promise<Response>((resolve) => {
        resolveSearch = resolve;
      });
    });
    render(<App />);
    const editor = await screen.findByLabelText('日记内容');
    fireEvent.change(editor, { target: { value: '# 未保存原文  \n' } });
    fireEvent.change(screen.getByLabelText('日记日期'), {
      target: { value: '2001-02-03' },
    });
    await openArchive();
    query('保留的搜索词');
    fireEvent.change(screen.getByLabelText('结束日期'), {
      target: { value: '2024-02-29' },
    });
    await submit();
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(searchSignal?.aborted).toBe(true);
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(editor).toHaveValue('# 未保存原文  \n');
    expect(screen.getByLabelText('日记日期')).toHaveValue('2001-02-03');
    await openArchive();
    expect(screen.getByLabelText('关键词')).toHaveValue('保留的搜索词');
    expect(screen.getByLabelText('结束日期')).toHaveValue('2024-02-29');
    expect(
      screen.queryByRole('region', { name: '搜索结果' }),
    ).not.toBeInTheDocument();
    await act(async () =>
      resolveSearch(json({ items: [sampleEntry], next_cursor: null })),
    );
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([path]) => path === '/api/v1/search'),
    ).toHaveLength(1);
  });

  it('removes search results and the hidden journal DOM on 401 while preserving the same-owner draft in memory', async () => {
    let searches = 0;
    mockApi((path) =>
      path === '/api/v1/search'
        ? ++searches === 1
          ? json({ items: [sampleEntry], next_cursor: 'next' })
          : json({}, 401)
        : undefined,
    );
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '登录后继续的私密草稿' },
    });
    await openArchive();
    query('私密搜索词');
    await submit();
    await userEvent.click(
      await screen.findByRole('button', { name: '加载更多结果' }),
    );
    await screen.findByLabelText('密码');
    expect(
      document.querySelector('textarea, .archive-workspace, .archive-entry'),
    ).toBeNull();
    expect(document.body.textContent).not.toContain('私密搜索词');
    expect(document.body.textContent).not.toContain('登录后继续的私密草稿');
    await logIn();
    await userEvent.click(await screen.findByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toHaveValue(
      '登录后继续的私密草稿',
    );
  });

  it('clears search inputs and results on explicit logout', async () => {
    mockApi((path) => {
      if (path === '/api/v1/auth/logout')
        return new Response(null, { status: 204 });
      if (path === '/api/v1/search')
        return json({ items: [sampleEntry], next_cursor: null });
      return undefined;
    });
    render(<App />);
    await openArchive();
    query('退出后清空');
    fireEvent.change(screen.getByLabelText('开始日期'), {
      target: { value: '2001-02-03' },
    });
    await submit();
    await screen.findByRole('article');
    await userEvent.click(screen.getByRole('button', { name: '退出登录' }));
    await logIn();
    await openArchive();
    expect(screen.getByLabelText('关键词')).toHaveValue('');
    expect(screen.getByLabelText('开始日期')).toHaveValue('');
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });

  it('preserves a conflicting draft and its resolution controls through archive navigation', async () => {
    const patches: Record<string, unknown>[] = [];
    const draft = '# 等待处理的冲突草稿  \n';
    const latest = {
      ...sampleEntry,
      content_md: '另一处保存的新版本',
      revision: 2,
    };
    mockApi(
      (path, options) => {
        if (path === `/api/v1/entries/${sampleEntry.id}`) {
          if (options.method === 'GET') return json(latest);
          if (options.method === 'PATCH') {
            patches.push(requestBody(options));
            return patches.length === 1
              ? json({ detail: { code: 'revision_conflict' } }, 409)
              : json({ ...latest, content_md: draft, revision: 3 });
          }
        }
        if (path === '/api/v1/search')
          return json({ items: [latest], next_cursor: null });
        return undefined;
      },
      [sampleEntry],
    );
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: '编辑' }));
    const editor = screen.getByLabelText('日记内容');
    fireEvent.change(editor, { target: { value: draft } });
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    await screen.findByText(/这篇日记已有新的版本/);

    const archive = await openArchive();
    query('新版本');
    await submit();
    await within(archive).findByText(latest.content_md);
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(editor).toHaveValue(draft);
    expect(screen.getByText(/这篇日记已有新的版本/)).toBeVisible();
    expect(screen.getByRole('button', { name: '保存修改' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '读取最新版本' })).toBeEnabled();
    expect(patches).toHaveLength(1);

    await userEvent.click(screen.getByRole('button', { name: '读取最新版本' }));
    await screen.findByText(latest.content_md);
    expect(editor).toHaveValue(draft);
    await userEvent.click(
      screen.getByRole('button', { name: '保留草稿，基于新版继续' }),
    );
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    await screen.findByText('日记已保存。');
    expect(patches.map((patch) => patch.expected_revision)).toEqual([1, 2]);
    expect(patches[1].content_md).toBe(draft);
  });

  it('disables archive navigation during journal writes and retains an uncertain create request through archive navigation', async () => {
    const bodies: Record<string, unknown>[] = [];
    let failWrite: (error: Error) => void = () => {};
    mockApi((path, options) => {
      if (path !== '/api/v1/entries' || options.method !== 'POST')
        return undefined;
      bodies.push(requestBody(options));
      if (bodies.length === 1)
        return new Promise<Response>((_, reject) => {
          failWrite = reject;
        });
      return json(sampleEntry);
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '只保存一次' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    expect(screen.getByRole('button', { name: '归档' })).toBeDisabled();
    await act(async () => failWrite(new TypeError('response lost')));
    await screen.findByText(/保存结果尚未确认/);
    await openArchive();
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('日记已保存。');
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toEqual(bodies[0]);
  });
});
