import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
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

const asset = {
  id: '4c4ed98e-f083-433f-aaf1-aa766407591e',
  mime_type: 'image/png',
  byte_size: 3,
  sha256: 'a'.repeat(64),
  width: 1,
  height: 1,
  created_at: sampleEntry.created_at,
};

describe('journal pinning', () => {
  it('pins with the observed revision, cancels old paging and preserves the frozen image draft', async () => {
    let completePin!: (response: Response) => void;
    let completePage!: (response: Response) => void;
    let pageSignal: AbortSignal | null = null;
    let pinned = false;
    const creates: Record<string, unknown>[] = [];
    const fetchMock = mockApi((path, options) => {
      if (path.startsWith('/api/v1/entries?')) {
        const params = new URL(path, 'http://127.0.0.1').searchParams;
        expect(params.get('order')).toBe('pinned');
        if (params.has('cursor')) {
          pageSignal = options.signal as AbortSignal;
          return new Promise<Response>((resolve) => {
            completePage = resolve;
          });
        }
        return json({
          items: [
            { ...sampleEntry, is_pinned: pinned, revision: pinned ? 2 : 1 },
          ],
          next_cursor: pinned ? null : 'old-page',
        });
      }
      if (path === '/api/v1/assets') return json(asset, 201);
      if (path === '/api/v1/entries' && options.method === 'POST') {
        creates.push(requestBody(options));
        if (creates.length === 1) throw new Error('response lost');
        return json(
          { ...sampleEntry, id: 'created-entry', assets: [asset] },
          201,
        );
      }
      if (
        path === `/api/v1/entries/${sampleEntry.id}` &&
        options.method === 'PATCH'
      ) {
        expect(requestBody(options)).toEqual({
          expected_revision: 1,
          is_pinned: true,
        });
        expect(options.headers).toMatchObject({
          'X-CSRF-Token': session.csrf_token,
        });
        return new Promise<Response>((resolve) => {
          completePin = resolve;
        });
      }
      return undefined;
    });
    render(<App />);
    await userEvent.click(
      await screen.findByRole('button', { name: '标签与图片' }),
    );
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '保留置顶期间的原文草稿' },
    });
    await userEvent.upload(
      screen.getByLabelText('选择图片'),
      new File(['png'], 'image.png', { type: 'image/png' }),
    );
    await screen.findByRole('button', { name: '移除图片 1' });
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByRole('button', { name: '重试保存' });
    await userEvent.click(screen.getByRole('button', { name: '加载更多日记' }));
    await userEvent.click(screen.getByRole('button', { name: '置顶' }));
    expect(pageSignal!.aborted).toBe(true);
    expect(screen.getByRole('button', { name: '退出登录' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '归档' })).toBeDisabled();
    pinned = true;
    await act(async () =>
      completePin(json({ ...sampleEntry, is_pinned: true, revision: 2 })),
    );
    await screen.findByText('日记已置顶。');
    await screen.findByRole('button', { name: '取消置顶' });
    await act(async () =>
      completePage(
        json({
          items: [
            { ...sampleEntry, id: 'stale', content_md: '不应回流的旧分页' },
          ],
          next_cursor: null,
        }),
      ),
    );
    expect(screen.queryByText('不应回流的旧分页')).not.toBeInTheDocument();
    expect(screen.getByLabelText('日记内容')).toHaveValue(
      '保留置顶期间的原文草稿',
    );
    expect(screen.getByRole('button', { name: '移除图片 1' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('日记已保存。');
    expect(creates[1]).toEqual(creates[0]);
    expect(creates[0].asset_ids).toEqual([asset.id]);
    expect(
      fetchMock.mock.calls.filter(
        ([path, options]) =>
          path === `/api/v1/entries/${sampleEntry.id}` &&
          options.method === 'PATCH',
      ),
    ).toHaveLength(1);
  });

  it('requires fresh reads after unpin conflicts or uncertain results without guessing the state', async () => {
    let attempts = 0;
    let serverPinned = true;
    const fetchMock = mockApi((path, options) => {
      if (path.startsWith('/api/v1/entries?'))
        return json({
          items: [{ ...sampleEntry, is_pinned: serverPinned }],
          next_cursor: null,
        });
      if (
        path === `/api/v1/entries/${sampleEntry.id}` &&
        options.method === 'PATCH'
      ) {
        attempts += 1;
        expect(requestBody(options)).toEqual({
          expected_revision: 1,
          is_pinned: false,
        });
        if (attempts === 1)
          return json({ detail: { code: 'revision_conflict' } }, 409);
        serverPinned = false;
        throw new Error('committed response lost');
      }
      return undefined;
    });
    render(<App />);
    await userEvent.click(
      await screen.findByRole('button', { name: '取消置顶' }),
    );
    await screen.findByText(
      '这篇日记已有修改，请刷新列表、核对置顶状态后再操作。',
    );
    expect(screen.getByRole('button', { name: '取消置顶' })).toBeDisabled();
    expect(screen.queryByText('已取消置顶。')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '刷新列表' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '取消置顶' })).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole('button', { name: '取消置顶' }));
    await screen.findByText(
      '置顶结果尚未确认。请刷新列表核对，再决定是否重试。',
    );
    expect(screen.getByRole('button', { name: '取消置顶' })).toBeDisabled();
    expect(
      screen.queryByRole('button', { name: '置顶' }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '刷新列表' }));
    await screen.findByRole('button', { name: '置顶' });
    expect(
      fetchMock.mock.calls.filter(
        ([path, options]) =>
          path === `/api/v1/entries/${sampleEntry.id}` &&
          options.method === 'PATCH',
      ),
    ).toHaveLength(2);
  });
});
