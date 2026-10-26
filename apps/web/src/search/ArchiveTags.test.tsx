import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '../App';
import { json, mockApi, requestBody, sampleEntry } from '../test/api-fixtures';

const tags = [
  {
    id: '11111111-1111-4111-8111-111111111111',
    name: '生活',
    created_at: sampleEntry.created_at,
  },
  {
    id: '22222222-2222-4222-8222-222222222222',
    name: '旅行',
    created_at: sampleEntry.created_at,
  },
];

describe('archive tag filters', () => {
  it('submits tag-only search and keeps submitted tags for pagination/retry while preserving the edited form on navigation', async () => {
    const bodies: Record<string, unknown>[] = [];
    let pages = 0;
    const fetchMock = mockApi((path, options) => {
      if (path.startsWith('/api/v1/tags?'))
        return path.includes('cursor=')
          ? json({ items: [tags[1]], next_cursor: null })
          : json({ items: [tags[0]], next_cursor: tags[0].id });
      if (path !== '/api/v1/search') return undefined;
      const body = requestBody(options);
      bodies.push(body);
      if (!body.cursor)
        return json({ items: [sampleEntry], next_cursor: 'next-tag-page' });
      return ++pages === 1
        ? json({}, 503)
        : json({
            items: [
              { ...sampleEntry, id: 'older', content_md: '标签分页结果' },
            ],
            next_cursor: null,
          });
    });
    render(<App />);
    const editor = await screen.findByLabelText('日记内容');
    fireEvent.change(editor, { target: { value: '保留的正文草稿' } });
    await userEvent.click(screen.getByRole('button', { name: '归档' }));
    await screen.findByRole('option', { name: '旅行' });
    await userEvent.selectOptions(screen.getByLabelText('标签'), tags[0].id);
    expect(bodies).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: '搜索日记' }));
    await screen.findByRole('button', { name: '加载更多结果' });
    await userEvent.selectOptions(screen.getByLabelText('标签'), tags[1].id);
    expect(screen.getByText(/已提交条件/)).toHaveTextContent('标签「生活」');
    expect(screen.getByText(/已提交条件/)).not.toHaveTextContent('旅行');
    await userEvent.click(screen.getByRole('button', { name: '加载更多结果' }));
    await userEvent.click(
      await screen.findByRole('button', { name: '重试搜索' }),
    );
    await screen.findByText('标签分页结果');
    expect(bodies).toEqual([
      {
        query: '',
        date_from: null,
        date_to: null,
        tag_id: tags[0].id,
        limit: 20,
        cursor: null,
      },
      {
        query: '',
        date_from: null,
        date_to: null,
        tag_id: tags[0].id,
        limit: 20,
        cursor: 'next-tag-page',
      },
      {
        query: '',
        date_from: null,
        date_to: null,
        tag_id: tags[0].id,
        limit: 20,
        cursor: 'next-tag-page',
      },
    ]);
    expect(
      fetchMock.mock.calls
        .filter(([path]) => path.includes('/search'))
        .every(([path]) => path === '/api/v1/search'),
    ).toBe(true);
    expect(window.location.search).toBe('');
    expect(localStorage.length + sessionStorage.length).toBe(0);
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(editor).toHaveValue('保留的正文草稿');
    await userEvent.click(screen.getByRole('button', { name: '归档' }));
    expect(screen.getByLabelText('标签')).toHaveValue(tags[1].id);
    expect(
      screen.queryByRole('region', { name: '搜索结果' }),
    ).not.toBeInTheDocument();
    expect(bodies).toHaveLength(3);
  });

  it('retries the tag catalog independently without blocking keyword/date search or sending a search automatically', async () => {
    const bodies: Record<string, unknown>[] = [];
    let failCatalog = false;
    mockApi((path, options) => {
      if (path.startsWith('/api/v1/tags?'))
        return failCatalog
          ? json({}, 503)
          : json({ items: tags, next_cursor: null });
      if (path !== '/api/v1/search') return undefined;
      bodies.push(requestBody(options));
      return json({ items: [], next_cursor: null });
    });
    render(<App />);
    await screen.findByLabelText('日记内容');
    await userEvent.click(
      await screen.findByRole('button', { name: '标签与图片' }),
    );
    await screen.findByRole('checkbox', { name: '生活' });
    failCatalog = true;
    await userEvent.click(screen.getByRole('button', { name: '归档' }));
    const archive = screen.getByRole('region', { name: '归档搜索' });
    await within(archive).findByText(/标签目录读取失败/);
    fireEvent.change(screen.getByLabelText('关键词'), {
      target: { value: '原文' },
    });
    fireEvent.change(screen.getByLabelText('开始日期'), {
      target: { value: '2000-01-01' },
    });
    await userEvent.click(screen.getByRole('button', { name: '搜索日记' }));
    await screen.findByText('没有找到符合条件的日记。');
    expect(bodies).toEqual([
      {
        query: '原文',
        date_from: '2000-01-01',
        date_to: null,
        limit: 20,
        cursor: null,
      },
    ]);
    failCatalog = false;
    await userEvent.click(
      within(archive).getByRole('button', { name: '重试读取标签' }),
    );
    await within(archive).findByRole('option', { name: '旅行' });
    expect(
      within(archive).queryByText(/标签目录读取失败/),
    ).not.toBeInTheDocument();
    expect(bodies).toHaveLength(1);
    await userEvent.selectOptions(screen.getByLabelText('标签'), tags[1].id);
    await userEvent.click(screen.getByRole('button', { name: '搜索日记' }));
    await screen.findByText('没有找到符合条件的日记。');
    expect(bodies[1]).toMatchObject({
      query: '原文',
      date_from: '2000-01-01',
      tag_id: tags[1].id,
    });
  });
});
