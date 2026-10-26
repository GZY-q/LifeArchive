import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from './App';
import { json, mockApi, sampleEntry } from './test/api-fixtures';

describe('quiet application layout', () => {
  it('keeps private navigation out of the signed-out shell', async () => {
    mockApi((path) => (path === '/api/v1/auth/me' ? json({}, 401) : undefined));
    render(<App />);
    expect(
      await screen.findByRole('heading', { name: '欢迎回来。' }),
    ).toBeVisible();
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.queryByText('owner')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '跳到主要内容' })).toHaveAttribute(
      'href',
      '#main',
    );
  });

  it('keeps navigation in the sidebar and preserves the editor across views', async () => {
    mockApi();
    render(<App />);
    const editor = await screen.findByLabelText('日记内容');
    fireEvent.change(editor, { target: { value: '今天散步，想留下这一刻。' } });
    const sidebar = screen.getByRole('complementary', { name: 'LifeArchive' });
    const navigation = within(sidebar).getByRole('navigation', {
      name: '主导航',
    });
    expect(within(navigation).getAllByRole('button')).toHaveLength(6);
    expect(
      within(navigation).getByRole('button', { name: '日记' }),
    ).toHaveAttribute('aria-current', 'page');
    await userEvent.click(
      within(navigation).getByRole('button', { name: '归档' }),
    );
    expect(
      screen.getByRole('heading', { level: 1, name: '归档' }),
    ).toBeVisible();
    expect(
      within(navigation).getByRole('button', { name: '归档' }),
    ).toHaveAttribute('aria-current', 'page');
    expect(editor).not.toBeVisible();
    await userEvent.click(
      within(navigation).getByRole('button', { name: '日记' }),
    );
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(editor).toBeVisible();
    expect(editor).toHaveValue('今天散步，想留下这一刻。');
  });

  it('discloses tools by keyboard without submitting or losing local input', async () => {
    const requests = mockApi();
    render(<App />);
    const editor = await screen.findByLabelText('日记内容');
    const toggle = screen.getByRole('button', { name: '标签与图片' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByLabelText('选择图片')).not.toBeVisible();
    fireEvent.change(editor, { target: { value: '# 保留原文  \n' } });
    toggle.focus();
    await userEvent.keyboard('{Enter}');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText('选择图片')).toBeVisible();
    fireEvent.change(screen.getByLabelText('新标签名称'), {
      target: { value: '未提交的标签' },
    });
    await userEvent.click(toggle);
    expect(screen.getByLabelText('新标签名称')).not.toBeVisible();
    await userEvent.click(toggle);
    expect(screen.getByLabelText('新标签名称')).toHaveValue('未提交的标签');
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(editor).toHaveValue('# 保留原文  \n');
    expect(
      requests.mock.calls.every(
        ([, options]) => !options.method || options.method === 'GET',
      ),
    ).toBe(true);
  });

  it('opens tools for an existing entry with selected tags', async () => {
    const tag = {
      id: 'tag-id',
      name: '日常',
      created_at: sampleEntry.created_at,
    };
    mockApi(
      (path) =>
        path.startsWith('/api/v1/tags?')
          ? json({ items: [tag], next_cursor: null })
          : undefined,
      [{ ...sampleEntry, tags: [tag] }],
    );
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: '编辑' }));
    expect(screen.getByRole('button', { name: '标签与图片' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(screen.getByRole('checkbox', { name: '日常' })).toBeChecked();
  });
});
