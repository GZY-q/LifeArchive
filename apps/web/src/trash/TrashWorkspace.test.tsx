import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
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
import { TrashWorkspace } from './TrashWorkspace';

const tag = { id: 'tag-id', name: '生活', created_at: sampleEntry.created_at };
const trashed = {
  ...sampleEntry,
  revision: 2,
  tags: [tag],
  deleted_at: '2026-10-02T04:00:00Z',
};
const restored = { ...trashed, revision: 3 };

describe('journal trash', () => {
  it('restores with the observed revision while preserving a frozen draft and refreshing journals', async () => {
    const creates: Record<string, unknown>[] = [];
    let completeRestore!: (value: Response) => void;
    let active = false;
    const fetchMock = mockApi((path, options) => {
      if (path.startsWith('/api/v1/tags?'))
        return json({ items: [tag], next_cursor: null });
      if (path.startsWith('/api/v1/trash?'))
        return json({ items: [trashed], next_cursor: null });
      if (path.startsWith('/api/v1/entries?'))
        return json({ items: active ? [restored] : [], next_cursor: null });
      if (path === '/api/v1/entries' && options.method === 'POST') {
        creates.push(requestBody(options));
        if (creates.length === 1) throw new Error('connection interrupted');
        return json(sampleEntry, 201);
      }
      if (path === `/api/v1/entries/${trashed.id}/restore`) {
        expect(requestBody(options)).toEqual({ expected_revision: 2 });
        expect(options.headers).toMatchObject({
          'X-CSRF-Token': session.csrf_token,
        });
        return new Promise<Response>((resolve) => {
          completeRestore = resolve;
        });
      }
      return undefined;
    });
    render(<App />);
    await userEvent.click(
      await screen.findByRole('button', { name: '标签与图片' }),
    );
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '未确认的原文草稿' },
    });
    await userEvent.click(
      await screen.findByRole('checkbox', { name: '生活' }),
    );
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByText(/保存结果尚未确认/);
    await userEvent.click(screen.getByRole('button', { name: '回收站' }));
    await userEvent.click(
      await screen.findByRole('button', { name: '恢复日记' }),
    );
    expect(screen.getByRole('button', { name: '日记' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '退出登录' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重新验证登录' })).toBeDisabled();
    active = true;
    await act(async () => completeRestore(json(restored)));
    await screen.findByText('日记已恢复，可回到日记列表查看。');
    expect(
      screen.queryByRole('button', { name: '恢复日记' }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toHaveValue('未确认的原文草稿');
    expect(screen.getByRole('checkbox', { name: '生活' })).toBeChecked();
    await screen.findByLabelText(`${sampleEntry.entry_date} 的日记`);
    await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('日记已保存。');
    expect(creates).toHaveLength(2);
    expect(creates[1]).toEqual(creates[0]);
    expect(creates[0].tag_ids).toEqual([tag.id]);
    expect(
      fetchMock.mock.calls.filter(([path]) => path.endsWith('/restore')),
    ).toHaveLength(1);
  });

  it('requires a refresh after restore conflicts and uncertain network results without retrying writes', async () => {
    let restores = 0;
    const fetchMock = mockApi((path) => {
      if (path.startsWith('/api/v1/trash?'))
        return json({ items: [trashed], next_cursor: null });
      if (path.endsWith('/restore')) {
        restores += 1;
        if (restores === 1)
          return json({ detail: { code: 'revision_conflict' } }, 409);
        throw new Error('connection interrupted');
      }
      return undefined;
    });
    render(
      <TrashWorkspace
        csrfToken={session.csrf_token}
        timezone={session.user.timezone}
        disabled={false}
        onBusy={vi.fn()}
        onRestored={vi.fn()}
        onExpired={vi.fn()}
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', { name: '恢复日记' }),
    );
    await screen.findByText('这篇日记的状态已有变化，请刷新回收站后核对。');
    expect(screen.getByRole('button', { name: '恢复日记' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '刷新回收站' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '恢复日记' })).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole('button', { name: '恢复日记' }));
    await screen.findByText(
      '恢复结果尚未确认。请刷新回收站核对，再决定是否重试。',
    );
    expect(
      screen.getByLabelText(`${trashed.entry_date} 的已删除日记`),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '恢复日记' })).toBeDisabled();
    expect(
      fetchMock.mock.calls.filter(([path]) => path.endsWith('/restore')),
    ).toHaveLength(2);
  });
});
