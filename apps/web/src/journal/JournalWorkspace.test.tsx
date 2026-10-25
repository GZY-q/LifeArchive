import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
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

describe('journal workflow', () => {
  it('creates and selects a tag, then freezes its IDs with an uncertain journal save', async () => {
    const tag = {
      id: '51f151a5-ed01-4e56-982d-4f4a6d98f5a8',
      name: '生活',
      created_at: sampleEntry.created_at,
    };
    const posts: Record<string, unknown>[] = [];
    mockApi((path, options) => {
      if (path === '/api/v1/tags' && options.method === 'POST') {
        expect(requestBody(options)).toEqual({ name: '生活' });
        expect(options.headers).toMatchObject({
          'X-CSRF-Token': session.csrf_token,
        });
        return json(tag, 201);
      }
      if (path === '/api/v1/entries' && options.method === 'POST') {
        posts.push(requestBody(options));
        return posts.length === 1
          ? Promise.reject(new TypeError('response lost'))
          : json({ ...sampleEntry, tags: [tag] });
      }
      return undefined;
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '今天散步' },
    });
    fireEvent.change(screen.getByLabelText('新标签名称'), {
      target: { value: '生活' },
    });
    await userEvent.click(
      screen.getByRole('button', { name: '创建并选择标签' }),
    );
    const choice = await screen.findByRole('checkbox', { name: '生活' });
    expect(choice).toBeChecked();
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByRole('button', { name: '重试保存' });
    expect(choice).toBeDisabled();
    expect(screen.getByLabelText('新标签名称')).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('日记已保存。');
    expect(posts[0].tag_ids).toEqual([tag.id]);
    expect(posts[1]).toEqual(posts[0]);
  });

  it('changes the tag filter without losing the draft or accepting a stale page', async () => {
    const tag = {
      id: '51f151a5-ed01-4e56-982d-4f4a6d98f5a8',
      name: '生活',
      created_at: sampleEntry.created_at,
    };
    let resolvePage!: (response: Response) => void;
    mockApi((path) => {
      if (path.startsWith('/api/v1/tags?'))
        return json({ items: [tag], next_cursor: null });
      if (path.includes('cursor=old-page'))
        return new Promise<Response>((resolve) => {
          resolvePage = resolve;
        });
      if (path.includes(`tag_id=${tag.id}`))
        return json({
          items: [{ ...sampleEntry, content_md: '标签内的记录', tags: [tag] }],
          next_cursor: null,
        });
      if (path.startsWith('/api/v1/entries?'))
        return json({ items: [sampleEntry], next_cursor: 'old-page' });
      return undefined;
    });
    render(<App />);
    const editor = await screen.findByLabelText('日记内容');
    fireEvent.change(editor, { target: { value: '尚未保存的草稿' } });
    await userEvent.click(
      await screen.findByRole('checkbox', { name: '生活' }),
    );
    await userEvent.click(
      await screen.findByRole('button', { name: '加载更多日记' }),
    );
    await userEvent.selectOptions(screen.getByLabelText('按标签筛选'), tag.id);
    await screen.findByText('标签内的记录');
    resolvePage(
      json({
        items: [{ ...sampleEntry, id: 'stale', content_md: '旧分页不得回来' }],
        next_cursor: null,
      }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText('日记内容')).toHaveValue('尚未保存的草稿'),
    );
    expect(editor).toBe(screen.getByLabelText('日记内容'));
    expect(screen.getByRole('checkbox', { name: '生活' })).toBeChecked();
    expect(screen.queryByText('旧分页不得回来')).not.toBeInTheDocument();
  });

  it('round-trips Chinese raw Markdown and a backdated date without submitting composition Enter', async () => {
    let stored: Record<string, unknown> | null = null;
    mockApi((path, options) => {
      if (path === '/api/v1/entries' && options.method === 'POST') {
        stored = requestBody(options);
        expect(options.headers).toMatchObject({
          'X-CSRF-Token': session.csrf_token,
          'X-LifeArchive-Request': '1',
        });
        return json({ ...sampleEntry, ...stored }, 201);
      }
      if (path.startsWith('/api/v1/entries?') && stored)
        return json({
          items: [{ ...sampleEntry, ...stored }],
          next_cursor: null,
        });
      return undefined;
    });
    render(<App />);
    const editor = await screen.findByLabelText('日记内容');
    const raw = '# 中文日记\n\n你好，世界！  \n<img src=x onerror=alert(1)>\n';
    fireEvent.compositionStart(editor);
    fireEvent.change(editor, { target: { value: raw } });
    fireEvent.keyDown(editor, {
      key: 'Enter',
      keyCode: 229,
      isComposing: true,
    });
    expect(screen.getByRole('button', { name: '保存日记' })).toBeDisabled();
    expect(stored).toBeNull();
    fireEvent.compositionEnd(editor);
    fireEvent.change(screen.getByLabelText('日记日期'), {
      target: { value: '2001-02-03' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByText('日记已保存。');
    expect(stored).toMatchObject({
      content_md: raw,
      entry_date: '2001-02-03',
      client_request_id: expect.any(String),
    });
    const card = await screen.findByRole('article', {
      name: '2001-02-03 的日记',
    });
    expect(card.querySelector('pre')!.textContent).toBe(raw);
    expect(card.querySelector('img')).toBeNull();
    expect(screen.getByLabelText('日记内容')).toHaveValue('');
  });

  it('reuses an unchanged request UUID after an uncertain save and freezes its payload', async () => {
    const posts: Record<string, unknown>[] = [];
    mockApi((path, options) => {
      if (path === '/api/v1/entries' && options.method === 'POST') {
        posts.push(requestBody(options));
        if (posts.length === 1)
          return Promise.reject(new TypeError('connection lost after commit'));
        return json(sampleEntry, 200);
      }
      return undefined;
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '只保存一次' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByText(/保存结果尚未确认/);
    expect(screen.getByLabelText('日记内容')).toBeDisabled();
    expect(screen.getByLabelText('日记日期')).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('日记已保存。');
    expect(posts).toHaveLength(2);
    expect(posts[1]).toEqual(posts[0]);
  });

  it.each([403, 404, 422])(
    'keeps an uncertain create UUID and body after a retry returns HTTP %i',
    async (status) => {
      const posts: Record<string, unknown>[] = [];
      mockApi((path, options) => {
        if (path === '/api/v1/entries' && options.method === 'POST') {
          posts.push(requestBody(options));
          if (posts.length === 1)
            return Promise.reject(new TypeError('response lost after commit'));
          if (posts.length === 2)
            return json({ detail: 'Rejected retry' }, status);
          return json(sampleEntry, 200);
        }
        return undefined;
      });
      render(<App />);
      fireEvent.change(await screen.findByLabelText('日记内容'), {
        target: { value: '首次可能已经保存' },
      });
      fireEvent.change(screen.getByLabelText('日记日期'), {
        target: { value: '2001-02-03' },
      });
      await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
      await screen.findByRole('button', { name: '重试保存' });
      await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
      await waitFor(() => expect(posts).toHaveLength(2));
      await waitFor(() =>
        expect(screen.getByRole('button', { name: '重试保存' })).toBeEnabled(),
      );
      expect(screen.getByLabelText('日记内容')).toBeDisabled();
      expect(screen.getByLabelText('日记日期')).toBeDisabled();
      expect(screen.getByLabelText('日记内容')).toHaveValue('首次可能已经保存');
      await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
      await screen.findByText('日记已保存。');
      expect(posts).toHaveLength(3);
      expect(posts[1]).toEqual(posts[0]);
      expect(posts[2]).toEqual(posts[0]);
    },
  );

  it('allows correcting the payload after an initial definite rejection', async () => {
    const posts: Record<string, unknown>[] = [];
    mockApi((path, options) => {
      if (path === '/api/v1/entries' && options.method === 'POST') {
        posts.push(requestBody(options));
        return posts.length === 1 ? json({}, 422) : json(sampleEntry, 201);
      }
      return undefined;
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '需要修正的内容' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByText('内容或日期格式不符合要求，请检查后重试。');
    expect(screen.getByLabelText('日记内容')).toBeEnabled();
    fireEvent.change(screen.getByLabelText('日记内容'), {
      target: { value: '修正后的内容' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByText('日记已保存。');
    expect(posts[1].client_request_id).not.toBe(posts[0].client_request_id);
    expect(posts[1].content_md).toBe('修正后的内容');
  });

  it('keeps a conflicting draft, reads the server version, and only saves again after explicit rebasing', async () => {
    const patches: Record<string, unknown>[] = [];
    const latest = {
      ...sampleEntry,
      content_md: '另一处保存的新版本',
      revision: 2,
    };
    mockApi(
      (path, options) => {
        if (
          path === `/api/v1/entries/${sampleEntry.id}` &&
          options.method === 'PATCH'
        ) {
          patches.push(requestBody(options));
          return patches.length === 1
            ? json({ detail: { code: 'revision_conflict' } }, 409)
            : json({ ...latest, content_md: '我的修改', revision: 3 });
        }
        if (
          path === `/api/v1/entries/${sampleEntry.id}` &&
          options.method === 'GET'
        )
          return json(latest);
        return undefined;
      },
      [sampleEntry],
    );
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: '编辑' }));
    fireEvent.change(screen.getByLabelText('日记内容'), {
      target: { value: '我的修改' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    await screen.findByText(/这篇日记已有新的版本/);
    expect(screen.getByLabelText('日记内容')).toHaveValue('我的修改');
    expect(screen.getByRole('button', { name: '保存修改' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '读取最新版本' }));
    await screen.findByText('另一处保存的新版本');
    expect(screen.getByLabelText('日记内容')).toHaveValue('我的修改');
    await userEvent.click(
      screen.getByRole('button', { name: '保留草稿，基于新版继续' }),
    );
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    await screen.findByText('日记已保存。');
    expect(patches.map((patch) => patch.expected_revision)).toEqual([1, 2]);
    expect(patches[1].content_md).toBe('我的修改');
  });

  it('requires confirmation for revision-checked deletion and keeps data visible if cancelled', async () => {
    let deleted = false;
    const confirm = vi
      .spyOn(window, 'confirm')
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    const fetchMock = mockApi((path, options) => {
      if (options.method === 'DELETE') {
        deleted = true;
        return new Response(null, { status: 204 });
      }
      if (path.startsWith('/api/v1/entries?'))
        return json({ items: deleted ? [] : [sampleEntry], next_cursor: null });
      return undefined;
    });
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: '删除' }));
    expect(deleted).toBe(false);
    expect(
      screen.getByRole('article', { name: `${sampleEntry.entry_date} 的日记` }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '删除' }));
    await screen.findByText('日记已删除。');
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(
      fetchMock.mock.calls.find(
        ([, options]) => options.method === 'DELETE',
      )?.[0],
    ).toBe(`/api/v1/entries/${sampleEntry.id}?expected_revision=1`);
    await screen.findByText('还没有记录');
  });

  it('displays paginated raw revisions safely and sends the revision cursor', async () => {
    const fetchMock = mockApi(
      (path) => {
        if (path.includes('/revisions?')) {
          const more = path.includes('before_revision=2');
          return json({
            items: [
              {
                revision: more ? 1 : 2,
                content_md: more ? '<script>private()</script>' : '较新版本',
                entry_date: sampleEntry.entry_date,
                changed_at: sampleEntry.updated_at,
                editor_id: session.user.id,
                tags: [],
              },
            ],
            next_cursor: more ? null : 2,
          });
        }
        return undefined;
      },
      [sampleEntry],
    );
    render(<App />);
    await userEvent.click(
      await screen.findByRole('button', { name: '修订历史' }),
    );
    await screen.findByText('较新版本');
    await userEvent.click(screen.getByRole('button', { name: '加载更早版本' }));
    await screen.findByText('<script>private()</script>');
    const region = screen.getByRole('region', { name: '修订历史' });
    expect(region.querySelector('script')).toBeNull();
    expect(within(region).getAllByRole('article')).toHaveLength(2);
    expect(
      fetchMock.mock.calls.some(([path]) =>
        path.endsWith('limit=20&before_revision=2'),
      ),
    ).toBe(true);
  });

  it('retries a failed list and loads the next opaque cursor without losing earlier entries', async () => {
    let requests = 0;
    mockApi((path) => {
      if (!path.startsWith('/api/v1/entries?')) return undefined;
      requests += 1;
      if (requests === 1) return json({}, 503);
      if (path.includes('cursor='))
        return json({
          items: [{ ...sampleEntry, id: 'older-id', entry_date: '2020-01-02' }],
          next_cursor: null,
        });
      return json({ items: [sampleEntry], next_cursor: 'opaque+/=' });
    });
    render(<App />);
    await userEvent.click(
      await screen.findByRole('button', { name: '重试读取日记' }),
    );
    await screen.findByRole('article', {
      name: `${sampleEntry.entry_date} 的日记`,
    });
    await userEvent.click(screen.getByRole('button', { name: '加载更多日记' }));
    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(2));
  });
});
