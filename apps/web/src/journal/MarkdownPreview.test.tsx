import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { Asset } from '../api/assets';
import { App } from '../App';
import { json, mockApi, requestBody, sampleEntry } from '../test/api-fixtures';

describe('journal Markdown preview integration', () => {
  it('keeps the editor, image selection and frozen creation body through local previews', async () => {
    const raw = '# 组合原文\n\n保留尾空格与 Unicode：🌱  \n';
    const asset: Asset = {
      id: 'a5eba42c-504a-4ebf-bf8f-95c3ca8bb9af',
      mime_type: 'image/png',
      byte_size: 3,
      sha256: 'a'.repeat(64),
      width: 1,
      height: 1,
      created_at: sampleEntry.created_at,
    };
    const creates: Record<string, unknown>[] = [];
    mockApi((path, options) => {
      if (path === '/api/v1/assets') return json(asset, 201);
      if (path === '/api/v1/entries' && options.method === 'POST') {
        creates.push(requestBody(options));
        return creates.length === 1
          ? Promise.reject(new TypeError('response lost'))
          : json({ ...sampleEntry, content_md: raw, assets: [asset] }, 201);
      }
      return undefined;
    });
    render(<App />);
    const editor = await screen.findByLabelText('日记内容');
    fireEvent.change(editor, { target: { value: raw } });
    fireEvent.compositionStart(editor);
    expect(screen.getByRole('button', { name: '预览草稿' })).toBeDisabled();
    fireEvent.compositionEnd(editor);
    await userEvent.upload(
      screen.getByLabelText('选择图片'),
      new File(['png'], 'private.png', { type: 'image/png' }),
    );
    await screen.findByRole('button', { name: '移除图片 1' });
    await userEvent.click(screen.getByRole('button', { name: '预览草稿' }));
    expect(
      within(screen.getByRole('region', { name: '草稿预览' })).getByRole(
        'heading',
        {
          name: '组合原文',
        },
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(editor).toHaveValue(raw);
    expect(creates).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: '归档' }));
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toBe(editor);
    expect(screen.getByRole('button', { name: '移除图片 1' })).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByRole('button', { name: '重试保存' });
    expect(editor).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '收起预览' }));
    await userEvent.click(screen.getByRole('button', { name: '预览草稿' }));
    expect(editor).toHaveValue(raw);
    expect(creates).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('日记已保存。');
    expect(creates).toHaveLength(2);
    expect(creates[1]).toEqual(creates[0]);
    expect(creates[0].content_md).toBe(raw);
    expect(creates[0].asset_ids).toEqual([asset.id]);
  });

  it('switches original and conflicting server content without changing the local draft or revision guard', async () => {
    const original = '# 原始记录\n\n原文尾空格  \n';
    const local = '# 本地草稿\n\n尚未覆盖服务器  \n';
    const latest = {
      ...sampleEntry,
      content_md: '# 服务器记录\n\n另一处修改',
      revision: 2,
    };
    const patches: Record<string, unknown>[] = [];
    mockApi(
      (path, options) => {
        if (path === `/api/v1/entries/${sampleEntry.id}`) {
          if (options.method === 'PATCH') {
            patches.push(requestBody(options));
            return patches.length === 1
              ? json({ detail: { code: 'revision_conflict' } }, 409)
              : json({ ...latest, content_md: local, revision: 3 });
          }
          if (options.method === 'GET') return json(latest);
        }
        return undefined;
      },
      [{ ...sampleEntry, content_md: original }],
    );
    render(<App />);
    const card = await screen.findByRole('article', {
      name: `${sampleEntry.entry_date} 的日记`,
    });
    expect(card.querySelector('pre')).toHaveTextContent('原文尾空格');
    expect(card.querySelector('pre')?.textContent).toBe(original);
    await userEvent.click(
      within(card).getByRole('button', { name: '预览 Markdown' }),
    );
    expect(
      within(card).getByRole('heading', { name: '原始记录' }),
    ).toBeInTheDocument();
    await userEvent.click(
      within(card).getByRole('button', { name: '查看原文' }),
    );
    expect(card.querySelector('pre')?.textContent).toBe(original);
    expect(patches).toHaveLength(0);
    await userEvent.click(within(card).getByRole('button', { name: '编辑' }));
    const editor = screen.getByLabelText('日记内容');
    fireEvent.change(editor, { target: { value: local } });
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    await screen.findByText(/这篇日记已有新的版本/);
    await userEvent.click(screen.getByRole('button', { name: '读取最新版本' }));
    const server = await screen.findByLabelText('服务器最新版本原文与预览');
    await userEvent.click(
      within(server).getByRole('button', { name: '预览 Markdown' }),
    );
    expect(
      within(server).getByRole('heading', { name: '服务器记录' }),
    ).toBeInTheDocument();
    expect(editor).toHaveValue(local);
    expect(screen.getByRole('button', { name: '保存修改' })).toBeDisabled();
    expect(patches).toHaveLength(1);
    await userEvent.click(
      screen.getByRole('button', { name: '保留草稿，基于新版继续' }),
    );
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    await screen.findByText('日记已保存。');
    expect(patches.map((patch) => patch.expected_revision)).toEqual([1, 2]);
    expect(patches.map((patch) => patch.content_md)).toEqual([local, local]);
  });
});
