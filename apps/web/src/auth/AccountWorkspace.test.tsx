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

const currentPassword = 'test-current-password';
const newPassword = '新密码保持原样  test-2026';
const image = {
  id: '3ebd828b-ea56-4ca3-9717-74bb787db710',
  mime_type: 'image/png',
  byte_size: 3,
  sha256: 'a'.repeat(64),
  width: 1,
  height: 1,
  created_at: sampleEntry.created_at,
};

function typePassword(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe('account security', () => {
  it('rotates password and sessions without losing a frozen image draft and uses the new CSRF', async () => {
    let completePassword!: (response: Response) => void;
    const creates: RequestInit[] = [];
    const firstRotation = { ...session, csrf_token: 'rotated-password-csrf' };
    const secondRotation = {
      ...session,
      csrf_token: 'rotated-revocation-csrf',
    };
    const fetchMock = mockApi((path, options) => {
      if (path === '/api/v1/assets') return json(image, 201);
      if (path === '/api/v1/entries' && options.method === 'POST') {
        creates.push(options);
        if (creates.length === 1) throw new Error('response lost');
        return json({ ...sampleEntry, assets: [image] }, 201);
      }
      if (path === '/api/v1/auth/password') {
        expect(requestBody(options)).toEqual({
          current_password: currentPassword,
          new_password: newPassword,
        });
        expect(options.headers).toMatchObject({
          'X-CSRF-Token': session.csrf_token,
        });
        return new Promise<Response>((resolve) => {
          completePassword = resolve;
        });
      }
      if (path === '/api/v1/auth/sessions/revoke') {
        expect(requestBody(options)).toEqual({ current_password: newPassword });
        expect(options.headers).toMatchObject({
          'X-CSRF-Token': firstRotation.csrf_token,
        });
        return json(secondRotation);
      }
      return undefined;
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '修改密码期间保留的草稿' },
    });
    await userEvent.upload(
      screen.getByLabelText('选择图片'),
      new File(['png'], 'image.png', { type: 'image/png' }),
    );
    await screen.findByRole('button', { name: '移除图片 1' });
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByRole('button', { name: '重试保存' });
    await userEvent.click(screen.getByRole('button', { name: '账户' }));
    typePassword('当前密码', currentPassword);
    typePassword('新密码', newPassword);
    typePassword('确认新密码', newPassword);
    await userEvent.click(screen.getByRole('button', { name: '保存新密码' }));
    expect(screen.getByRole('button', { name: '日记' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '退出登录' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重新验证登录' })).toBeDisabled();
    await act(async () => completePassword(json(firstRotation)));
    await screen.findByText('密码已更新，其他会话已退出；本页草稿仍保留。');
    for (const label of ['当前密码', '新密码', '确认新密码'])
      expect(screen.getByLabelText(label)).toHaveValue('');
    typePassword('当前密码', newPassword);
    await userEvent.click(screen.getByRole('button', { name: '退出其他会话' }));
    await screen.findByText('其他会话已退出，当前页面可继续使用。');
    expect(screen.getByLabelText('当前密码')).toHaveValue('');
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toHaveValue(
      '修改密码期间保留的草稿',
    );
    expect(screen.getByRole('button', { name: '移除图片 1' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('日记已保存。');
    expect(requestBody(creates[1])).toEqual(requestBody(creates[0]));
    expect(requestBody(creates[1]).asset_ids).toEqual([image.id]);
    expect(creates[1].headers).toMatchObject({
      'X-CSRF-Token': secondRotation.csrf_token,
    });
    expect(
      fetchMock.mock.calls.filter(([path]) => path === '/api/v1/auth/password'),
    ).toHaveLength(1);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('keeps invalid-password sessions, blocks uncertain retries across navigation and preserves drafts through 401', async () => {
    let requests = 0;
    let checks = 0;
    mockApi((path) => {
      if (path === '/api/v1/auth/me')
        return json({
          ...session,
          csrf_token: ++checks === 1 ? session.csrf_token : 'verified-csrf',
        });
      if (path === '/api/v1/auth/sessions/revoke') {
        requests += 1;
        if (requests === 1)
          return json({ detail: { code: 'invalid_current_password' } }, 403);
        if (requests === 2) throw new Error('response lost');
        return json({}, 401);
      }
      return undefined;
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '会话失效也保留的草稿' },
    });
    await userEvent.click(screen.getByRole('button', { name: '账户' }));
    typePassword('当前密码', 'incorrect');
    await userEvent.click(screen.getByRole('button', { name: '退出其他会话' }));
    await screen.findByText('当前密码不正确，请重新输入。');
    expect(screen.getByLabelText('当前密码')).toHaveValue('');
    expect(screen.queryByLabelText('用户名')).not.toBeInTheDocument();
    typePassword('当前密码', currentPassword);
    await userEvent.click(screen.getByRole('button', { name: '退出其他会话' }));
    await screen.findByText(/操作结果尚未确认/);
    expect(screen.getByRole('button', { name: '退出其他会话' })).toBeDisabled();
    expect(screen.getByLabelText('当前密码')).toHaveValue('');
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    await userEvent.click(screen.getByRole('button', { name: '账户' }));
    expect(screen.getByRole('button', { name: '退出其他会话' })).toBeDisabled();
    expect(requests).toBe(2);
    await userEvent.click(screen.getByRole('button', { name: '重新验证登录' }));
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: '退出其他会话' }),
      ).toBeEnabled(),
    );
    expect(screen.queryByText(/操作结果尚未确认/)).not.toBeInTheDocument();
    typePassword('当前密码', currentPassword);
    await userEvent.click(screen.getByRole('button', { name: '退出其他会话' }));
    await screen.findByLabelText('用户名');
    expect(document.body.textContent).not.toContain('会话失效也保留的草稿');
    fireEvent.change(screen.getByLabelText('用户名'), {
      target: { value: 'owner' },
    });
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: currentPassword },
    });
    await userEvent.click(screen.getByRole('button', { name: '登录' }));
    await screen.findByLabelText('当前密码');
    expect(screen.getByLabelText('当前密码')).toHaveValue('');
    await userEvent.click(screen.getByRole('button', { name: '日记' }));
    expect(screen.getByLabelText('日记内容')).toHaveValue(
      '会话失效也保留的草稿',
    );
    expect(requests).toBe(3);
  });
});
