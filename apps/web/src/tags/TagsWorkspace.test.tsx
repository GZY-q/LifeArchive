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

import type { Tag } from '../api/tags';
import { App } from '../App';
import { json, mockApi, requestBody, sampleEntry } from '../test/api-fixtures';
import { TagsWorkspace } from './TagsWorkspace';

const original: Tag = {
  id: '31d57308-e942-4b86-a3b7-7d5813bd50a3',
  name: '生活',
  created_at: '2026-10-01T00:00:00Z',
};

describe('tag renaming', () => {
  it('refreshes current names and keeps the same editor, selected filter and frozen creation request', async () => {
    let tag = original;
    const creates: Record<string, unknown>[] = [];
    const patches: Record<string, unknown>[] = [];
    let complete: ((response: Response) => void) | undefined;
    const fetchMock = mockApi((path, options) => {
      if (path.startsWith('/api/v1/tags?'))
        return json({ items: [tag], next_cursor: null });
      if (path.startsWith('/api/v1/entries?'))
        return json({
          items: [{ ...sampleEntry, tags: [tag] }],
          next_cursor: null,
        });
      if (path === `/api/v1/tags/${original.id}`) {
        patches.push(requestBody(options));
        return new Promise<Response>((resolve) => {
          complete = resolve;
        });
      }
      if (path === '/api/v1/entries' && options.method === 'POST') {
        creates.push(requestBody(options));
        return creates.length === 1
          ? Promise.reject(new TypeError('response lost'))
          : json({ ...sampleEntry, tags: [tag] }, 201);
      }
      return undefined;
    });
    render(<App />);
    await userEvent.click(
      await screen.findByRole('button', { name: '标签与图片' }),
    );
    const editor = await screen.findByLabelText('日记内容');
    await userEvent.click(
      await screen.findByRole('checkbox', { name: '生活' }),
    );
    await userEvent.selectOptions(
      screen.getByLabelText('按标签筛选'),
      original.id,
    );
    fireEvent.change(editor, {
      target: { value: '保留原文与创建 UUID  🌱  \n' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByRole('button', { name: '重试保存' });
    await userEvent.click(screen.getByRole('button', { name: '标签管理' }));
    await userEvent.click(
      await screen.findByRole('button', { name: '改名 生活' }),
    );
    const input = screen.getByRole('textbox', { name: '新标签名称' });
    fireEvent.change(input, { target: { value: '日常' } });
    expect(patches).toHaveLength(0);
    fireEvent.compositionStart(input);
    fireEvent.submit(input.closest('form')!);
    expect(patches).toHaveLength(0);
    fireEvent.compositionEnd(input);
    await userEvent.click(screen.getByRole('button', { name: '保存标签名称' }));
    expect(screen.getByRole('button', { name: '日记' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '退出登录' })).toBeDisabled();
    expect(patches).toEqual([{ name: '日常', expected_name: '生活' }]);
    tag = { ...tag, name: '日常' };
    complete!(json(tag));
    await screen.findByText(/标签名称已更新/);
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(editor).toHaveValue('保留原文与创建 UUID  🌱  \n');
    expect(screen.getByLabelText('按标签筛选')).toHaveValue(original.id);
    expect(await screen.findByRole('checkbox', { name: '日常' })).toBeChecked();
    expect(editor).toBeDisabled();
    const card = screen.getByRole('article', {
      name: `${sampleEntry.entry_date} 的日记`,
    });
    expect(await within(card).findByText('日常')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('日记已保存。');
    expect(creates).toHaveLength(2);
    expect(creates[1]).toEqual(creates[0]);
    expect(creates[0].tag_ids).toEqual([original.id]);
    const patchCall = fetchMock.mock.calls.find(
      ([path]) => path === `/api/v1/tags/${original.id}`,
    )!;
    expect(patchCall[1]).toMatchObject({
      method: 'PATCH',
      headers: {
        'X-CSRF-Token': 'test-csrf-token',
        'X-LifeArchive-Request': '1',
      },
    });
  });

  it.each(['conflict', 'name_taken', 'network', 'server', 'invalid'] as const)(
    'requires a fresh catalogue and explicit edit after %s, retaining the typed name',
    async (failure) => {
      let tag = original;
      const patches: Record<string, unknown>[] = [];
      mockApi((path, options) => {
        if (path.startsWith('/api/v1/tags?'))
          return json({ items: [tag], next_cursor: null });
        if (path === `/api/v1/tags/${original.id}`) {
          patches.push(requestBody(options));
          if (patches.length === 1) {
            tag = { ...tag, name: '其他页面的名称' };
            if (failure === 'conflict' || failure === 'name_taken')
              return json(
                {
                  detail: {
                    code:
                      failure === 'conflict'
                        ? 'tag_conflict'
                        : 'tag_name_taken',
                  },
                },
                409,
              );
            if (failure === 'server') return json({}, 503);
            if (failure === 'invalid') return json({});
            return Promise.reject(new TypeError('response lost'));
          }
          tag = { ...tag, name: '用户输入' };
          return json(tag);
        }
        return undefined;
      });
      const onCatalogue = vi.fn();
      render(
        <TagsWorkspace
          csrfToken="csrf"
          disabled={false}
          onExpired={vi.fn()}
          onBusy={vi.fn()}
          onCatalogue={onCatalogue}
        />,
      );
      await userEvent.click(
        await screen.findByRole('button', { name: '改名 生活' }),
      );
      fireEvent.change(screen.getByRole('textbox', { name: '新标签名称' }), {
        target: { value: '用户输入' },
      });
      await userEvent.click(
        screen.getByRole('button', { name: '保存标签名称' }),
      );
      await screen.findByRole('alert');
      expect(screen.getByRole('textbox', { name: '新标签名称' })).toHaveValue(
        '用户输入',
      );
      expect(
        screen.getByRole('button', { name: '保存标签名称' }),
      ).toBeDisabled();
      expect(screen.getByRole('button', { name: '改名 生活' })).toBeDisabled();
      await userEvent.click(
        screen.getByRole('button', { name: '重新读取标签目录' }),
      );
      await screen.findByRole('button', { name: '改名 其他页面的名称' });
      expect(
        screen.getByRole('button', { name: '保存标签名称' }),
      ).toBeDisabled();
      expect(screen.getByRole('textbox', { name: '新标签名称' })).toHaveValue(
        '用户输入',
      );
      await userEvent.click(
        screen.getByRole('button', { name: '改名 其他页面的名称' }),
      );
      await userEvent.click(
        screen.getByRole('button', { name: '保存标签名称' }),
      );
      await screen.findByText(/标签名称已更新/);
      expect(patches).toEqual([
        { name: '用户输入', expected_name: '生活' },
        { name: '用户输入', expected_name: '其他页面的名称' },
      ]);
      await waitFor(() => expect(onCatalogue).toHaveBeenCalledTimes(3));
    },
  );

  it('ignores a rename response after the workspace unmounts', async () => {
    let complete: ((response: Response) => void) | undefined;
    mockApi((path) => {
      if (path.startsWith('/api/v1/tags?'))
        return json({ items: [original], next_cursor: null });
      if (path === `/api/v1/tags/${original.id}`)
        return new Promise<Response>((resolve) => {
          complete = resolve;
        });
      return undefined;
    });
    const onCatalogue = vi.fn();
    const onBusy = vi.fn();
    const onExpired = vi.fn();
    const { unmount } = render(
      <TagsWorkspace
        csrfToken="csrf"
        disabled={false}
        onExpired={onExpired}
        onBusy={onBusy}
        onCatalogue={onCatalogue}
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', { name: '改名 生活' }),
    );
    fireEvent.change(screen.getByRole('textbox', { name: '新标签名称' }), {
      target: { value: '日常' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存标签名称' }));
    expect(onBusy).toHaveBeenCalledExactlyOnceWith(true);
    unmount();
    await act(async () => {
      complete!(json({ ...original, name: '日常' }));
    });
    expect(onCatalogue).toHaveBeenCalledTimes(1);
    expect(onBusy).toHaveBeenCalledTimes(1);
    expect(onExpired).not.toHaveBeenCalled();
  });
});
