import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { Asset } from '../api/assets';
import { App } from '../App';
import {
  json,
  mockApi,
  requestBody,
  sampleEntry,
  session,
} from '../test/api-fixtures';
import { AssetGallery } from './AssetGallery';

const asset: Asset = {
  id: 'a5eba42c-504a-4ebf-bf8f-95c3ca8bb9af',
  mime_type: 'image/png',
  byte_size: 3,
  sha256: 'a'.repeat(64),
  width: 1,
  height: 1,
  created_at: sampleEntry.created_at,
};

describe('private journal images', () => {
  it('uploads raw bytes with a write lock and preserves image IDs through navigation, expiry and frozen creation retry', async () => {
    let completeUpload!: (response: Response) => void;
    const creates: Record<string, unknown>[] = [];
    const file = new File(['png'], 'private-name.png', { type: 'image/png' });
    mockApi((path, options) => {
      if (path === '/api/v1/assets') {
        expect(options.body).toBe(file);
        expect(options.headers).toMatchObject({
          'Content-Type': 'image/png',
          'X-CSRF-Token': session.csrf_token,
          'X-LifeArchive-Request': '1',
        });
        return new Promise<Response>((resolve) => {
          completeUpload = resolve;
        });
      }
      if (path === '/api/v1/entries' && options.method === 'POST') {
        creates.push(requestBody(options));
        return creates.length === 1
          ? json({}, 401)
          : json({ ...sampleEntry, assets: [asset] }, 201);
      }
      return undefined;
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '保留图片和原文草稿' },
    });
    await userEvent.upload(screen.getByLabelText('选择图片'), file);
    expect(screen.getByRole('button', { name: '保存日记' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '退出登录' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '归档' })).toBeDisabled();
    await act(async () => completeUpload(json(asset, 201)));
    await screen.findByRole('button', { name: '移除图片 1' });
    await userEvent.click(screen.getByRole('button', { name: '归档' }));
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByRole('button', { name: '移除图片 1' })).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await userEvent.type(await screen.findByLabelText('用户名'), 'owner');
    await userEvent.type(screen.getByLabelText('密码'), 'test-password');
    await userEvent.click(screen.getByRole('button', { name: '登录' }));
    await screen.findByRole('button', { name: '重试保存' });
    expect(screen.getByLabelText('日记内容')).toHaveValue('保留图片和原文草稿');
    expect(screen.getByRole('button', { name: '移除图片 1' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('日记已保存。');
    expect(creates).toHaveLength(2);
    expect(creates[1]).toEqual(creates[0]);
    expect(creates[0].asset_ids).toEqual([asset.id]);
  });

  it('reads originals only when expanded, revokes object URLs and forwards media expiry', async () => {
    const createObjectURL = vi.fn(() => 'blob:private-original');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal(
      'URL',
      class extends URL {
        static createObjectURL = createObjectURL;
        static revokeObjectURL = revokeObjectURL;
      },
    );
    const expired = vi.fn();
    let reads = 0;
    const fetchMock = mockApi((path, options) => {
      if (path === `/api/v1/assets/${asset.id}`) {
        expect(options.credentials).toBe('same-origin');
        expect(options.cache).toBe('no-store');
        return ++reads === 1
          ? new Response('png', { headers: { 'Content-Type': 'image/png' } })
          : json({}, 401);
      }
      return undefined;
    });
    render(<AssetGallery assets={[asset]} onExpired={expired} />);
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole('button', { name: '查看图片（1）' }),
    );
    expect(
      await screen.findByRole('img', { name: '日记图片附件' }),
    ).toHaveAttribute('src', 'blob:private-original');
    expect(screen.getByRole('link', { name: '下载原图' })).toHaveAttribute(
      'download',
      `image-${asset.id}.png`,
    );
    await userEvent.click(screen.getByRole('button', { name: '收起图片' }));
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:private-original');
    await userEvent.click(
      screen.getByRole('button', { name: '查看图片（1）' }),
    );
    await waitFor(() => expect(expired).toHaveBeenCalledOnce());
    expect(createObjectURL).toHaveBeenCalledOnce();
  });

  it('retains uploaded selections after an uncertain upload and deduplicates a manual retry', async () => {
    let uploads = 0;
    let saved: Record<string, unknown> | null = null;
    mockApi((path, options) => {
      if (path === '/api/v1/assets') {
        uploads += 1;
        if (uploads === 2) throw new Error('connection interrupted');
        return json(asset, uploads === 1 ? 201 : 200);
      }
      if (path === '/api/v1/entries' && options.method === 'POST') {
        saved = requestBody(options);
        return json({ ...sampleEntry, assets: [asset] }, 201);
      }
      return undefined;
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '上传失败也保留选择' },
    });
    const file = new File(['png'], 'image.png', { type: 'image/png' });
    await userEvent.upload(screen.getByLabelText('选择图片'), file);
    await screen.findByRole('button', { name: '移除图片 1' });
    await userEvent.upload(screen.getByLabelText('选择图片'), file);
    await screen.findByText(/可重新选择同一文件重试/);
    expect(screen.getByRole('button', { name: '移除图片 1' })).toBeEnabled();
    await userEvent.upload(screen.getByLabelText('选择图片'), file);
    await waitFor(() =>
      expect(
        screen.queryByText(/可重新选择同一文件重试/),
      ).not.toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByText('日记已保存。');
    expect(saved).toMatchObject({ asset_ids: [asset.id] });
    expect(uploads).toBe(3);
  });
});
