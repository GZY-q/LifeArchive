import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { App } from '../App';
import { json, mockApi, requestBody } from '../test/api-fixtures';
import { ExportWorkspace } from './ExportWorkspace';

function objectUrls() {
  const create = vi
    .fn()
    .mockReturnValueOnce('blob:export-1')
    .mockReturnValue('blob:export-2');
  const revoke = vi.fn();
  vi.stubGlobal(
    'URL',
    class extends URL {
      static createObjectURL = create;
      static revokeObjectURL = revoke;
    },
  );
  return { create, revoke };
}

function archive() {
  return new Response('PK-synthetic-zip', {
    headers: { 'Content-Type': 'application/zip' },
  });
}

describe('journal export', () => {
  it('only generates explicitly, binds the download to its options and keeps the editor and draft', async () => {
    const urls = objectUrls();
    const bodies: Record<string, unknown>[] = [];
    let finish!: (response: Response) => void;
    const fetchMock = mockApi((path, options) => {
      if (path === '/api/v1/journal-export') {
        bodies.push(requestBody(options));
        if (bodies.length === 1)
          return new Promise<Response>((resolve) => {
            finish = resolve;
          });
        return archive();
      }
      return undefined;
    });
    render(<App />);
    const editor = await screen.findByLabelText('日记内容');
    fireEvent.change(editor, { target: { value: '  保留草稿 😀\n' } });
    await userEvent.click(screen.getByRole('button', { name: '导出' }));
    expect(bodies).toEqual([]);
    const deleted = screen.getByRole('checkbox', {
      name: /包含回收站中的日记/,
    });
    expect(deleted).not.toBeChecked();
    await userEvent.click(screen.getByRole('button', { name: '生成导出文件' }));
    expect(deleted).toBeDisabled();
    expect(screen.getByRole('button', { name: '正在生成…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '日记' })).toBeEnabled();
    await act(async () => finish(archive()));
    const link = await screen.findByRole('link', { name: '下载日记 ZIP' });
    expect(link).toHaveAttribute('href', 'blob:export-1');
    expect(link).toHaveAttribute('download', 'life-archive-journal.zip');
    const panel = within(screen.getByRole('region', { name: '导出日记' }));
    expect(panel.getByRole('status')).toHaveTextContent('仅活动日记');
    const call = fetchMock.mock.calls.find(
      ([path]) => path === '/api/v1/journal-export',
    )!;
    expect(call[1]).toMatchObject({
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        Accept: 'application/zip',
        'X-CSRF-Token': 'test-csrf-token',
        'X-LifeArchive-Request': '1',
        'Content-Type': 'application/json',
      },
    });
    await userEvent.click(deleted);
    expect(
      screen.queryByRole('link', { name: '下载日记 ZIP' }),
    ).not.toBeInTheDocument();
    expect(urls.revoke).toHaveBeenCalledWith('blob:export-1');
    await userEvent.click(screen.getByRole('button', { name: '生成导出文件' }));
    await screen.findByRole('link', { name: '下载日记 ZIP' });
    expect(panel.getByRole('status')).toHaveTextContent('包含回收站');
    expect(bodies).toEqual([
      { include_deleted: false },
      { include_deleted: true },
    ]);
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(editor).toHaveValue('  保留草稿 😀\n');
    expect(urls.revoke).toHaveBeenCalledWith('blob:export-2');
  });

  it('aborts a read on navigation and ignores a late archive without creating a URL', async () => {
    const urls = objectUrls();
    let finish!: (response: Response) => void;
    let signal!: AbortSignal;
    mockApi((path, options) => {
      if (path === '/api/v1/journal-export') {
        signal = options.signal!;
        return new Promise<Response>((resolve) => {
          finish = resolve;
        });
      }
      return undefined;
    });
    render(<App />);
    const editor = await screen.findByLabelText('日记内容');
    fireEvent.change(editor, { target: { value: '下载取消仍保留草稿' } });
    await userEvent.click(screen.getByRole('button', { name: '导出' }));
    await userEvent.click(screen.getByRole('button', { name: '生成导出文件' }));
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(signal.aborted).toBe(true);
    await act(async () => finish(archive()));
    expect(urls.create).not.toHaveBeenCalled();
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(editor).toHaveValue('下载取消仍保留草稿');
  });

  it('does not offer failed or invalid downloads and only retries after another click', async () => {
    const urls = objectUrls();
    const responses = [
      json({}, 413),
      json({}, 429),
      json({}, 503),
      json({}, 504),
      new Response('not a ZIP', { headers: { 'Content-Type': 'text/plain' } }),
    ];
    let requests = 0;
    mockApi((path) => {
      if (path !== '/api/v1/journal-export') return undefined;
      requests += 1;
      return responses.shift() ?? archive();
    });
    const timer = vi.spyOn(window, 'setTimeout');
    render(
      <ExportWorkspace csrfToken="csrf" disabled={false} onExpired={vi.fn()} />,
    );
    for (const message of [
      /超出网页导出上限/,
      /已有导出/,
      /检查服务和原图/,
      /超时/,
      /尚未取得完整/,
    ]) {
      await userEvent.click(
        screen.getByRole('button', { name: '生成导出文件' }),
      );
      expect(await screen.findByRole('alert')).toHaveTextContent(message);
      expect(
        screen.queryByRole('link', { name: '下载日记 ZIP' }),
      ).not.toBeInTheDocument();
    }
    expect(requests).toBe(5);
    expect(urls.create).not.toHaveBeenCalled();
    expect(timer).toHaveBeenCalledWith(expect.any(Function), 45_000);
    await userEvent.click(screen.getByRole('button', { name: '生成导出文件' }));
    await screen.findByRole('link', { name: '下载日记 ZIP' });
    expect(requests).toBe(6);
  });

  it('uses the existing login guard on 401 and preserves the journal draft after login', async () => {
    const urls = objectUrls();
    let requests = 0;
    mockApi((path) => {
      if (path !== '/api/v1/journal-export') return undefined;
      requests += 1;
      return json({}, 401);
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '重新登录后继续写' },
    });
    await userEvent.click(screen.getByRole('button', { name: '导出' }));
    await userEvent.click(screen.getByRole('button', { name: '生成导出文件' }));
    await userEvent.type(await screen.findByLabelText('用户名'), 'owner');
    expect(screen.getByRole('alert')).toHaveTextContent(
      '未保存草稿仅在当前页面内存中保留',
    );
    await userEvent.type(screen.getByLabelText('密码'), 'test-password');
    await userEvent.click(screen.getByRole('button', { name: '登录' }));
    await screen.findByRole('button', { name: '生成导出文件' });
    expect(requests).toBe(1);
    expect(urls.create).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    await waitFor(() =>
      expect(screen.getByLabelText('日记内容')).toHaveValue('重新登录后继续写'),
    );
  });
});
