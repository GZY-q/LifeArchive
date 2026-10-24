import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

async function signIn() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('用户名'), 'owner');
  await user.type(screen.getByLabelText('密码'), 'test-password');
  await user.click(screen.getByRole('button', { name: '登录' }));
  return user;
}

describe('private owner session', () => {
  it('refreshes a rotated session token without discarding the current draft', async () => {
    let checks = 0;
    const writes: RequestInit[] = [];
    mockApi((path, options) => {
      if (path === '/api/v1/auth/me')
        return json({
          ...session,
          csrf_token: ++checks === 1 ? 'old-token' : 'new-token',
        });
      if (path === '/api/v1/entries' && options.method === 'POST') {
        writes.push(options);
        return writes.length === 1 ? json({}, 403) : json(sampleEntry, 201);
      }
      return undefined;
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '保留这份草稿' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByText(/安全校验未通过/);
    await userEvent.click(screen.getByRole('button', { name: '重新验证登录' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '保存日记' })).toBeEnabled(),
    );
    expect(screen.getByLabelText('日记内容')).toHaveValue('保留这份草稿');
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByText('日记已保存。');
    expect(writes[1].headers).toMatchObject({ 'X-CSRF-Token': 'new-token' });
  });
  it('does not request or show journals before a successful login', async () => {
    const fetchMock = mockApi(
      (path) =>
        path === '/api/v1/auth/me'
          ? json({ detail: 'Unauthorized' }, 401)
          : undefined,
      [sampleEntry],
    );
    render(<App />);
    await screen.findByLabelText('用户名');
    expect(screen.queryByLabelText('日记内容')).not.toBeInTheDocument();
    expect(screen.queryByText(sampleEntry.content_md)).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([path]) => path.startsWith('/api/v1/entries')),
    ).toBe(false);
    expect(
      screen.queryByRole('button', { name: /注册/ }),
    ).not.toBeInTheDocument();
    await signIn();
    await screen.findByLabelText('日记内容');
    const call = fetchMock.mock.calls.find(
      ([path]) => path === '/api/v1/auth/login',
    )!;
    expect(requestBody(call[1])).toEqual({
      username: 'owner',
      password: 'test-password',
    });
    expect(call[1].credentials).toBe('same-origin');
    expect(call[1].headers).toMatchObject({
      'X-LifeArchive-Request': '1',
      'Content-Type': 'application/json',
    });
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('reports a failed login and clears the password field', async () => {
    mockApi((path) =>
      path.startsWith('/api/v1/auth/')
        ? json({ detail: 'Unauthorized' }, 401)
        : undefined,
    );
    render(<App />);
    await screen.findByLabelText('密码');
    await signIn();
    expect(await screen.findByText('用户名或密码不正确。')).toBeInTheDocument();
    expect(screen.getByLabelText('密码')).toHaveValue('');
    expect(screen.queryByLabelText('日记内容')).not.toBeInTheDocument();
  });

  it('hides private DOM on 401 and restores the same in-memory draft and request ID after login', async () => {
    const posts: Record<string, unknown>[] = [];
    mockApi(
      (path, options) => {
        if (path === '/api/v1/entries' && options.method === 'POST') {
          posts.push(requestBody(options));
          return posts.length === 1
            ? json({}, 401)
            : json({ ...sampleEntry, content_md: '未保存的私人内容' }, 201);
        }
        return undefined;
      },
      [sampleEntry],
    );
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '未保存的私人内容' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存日记' }));
    await screen.findByLabelText('密码');
    expect(screen.getByRole('alert')).toHaveTextContent(
      '草稿仅在当前页面内存中保留',
    );
    expect(screen.queryByLabelText('日记内容')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('未保存的私人内容');
    expect(document.body.textContent).not.toContain('今天的记录');
    await signIn();
    expect(await screen.findByLabelText('日记内容')).toHaveValue(
      '未保存的私人内容',
    );
    await userEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('日记已保存。');
    expect(posts[1]).toEqual(posts[0]);
  });

  it('confirms unsaved content before logout, sends CSRF, and clears the draft after logout', async () => {
    const fetchMock = mockApi((path) =>
      path === '/api/v1/auth/logout'
        ? new Response(null, { status: 204 })
        : undefined,
    );
    const confirm = vi
      .spyOn(window, 'confirm')
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    render(<App />);
    fireEvent.change(await screen.findByLabelText('日记内容'), {
      target: { value: '退出前的草稿' },
    });
    await userEvent.click(screen.getByRole('button', { name: '退出登录' }));
    expect(
      fetchMock.mock.calls.some(([path]) => path === '/api/v1/auth/logout'),
    ).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: '退出登录' }));
    await screen.findByLabelText('密码');
    expect(confirm).toHaveBeenCalledTimes(2);
    const call = fetchMock.mock.calls.find(
      ([path]) => path === '/api/v1/auth/logout',
    )!;
    expect(call[1].headers).toMatchObject({
      'X-CSRF-Token': session.csrf_token,
      'X-LifeArchive-Request': '1',
    });
    await signIn();
    expect(await screen.findByLabelText('日记内容')).toHaveValue('');
    expect(localStorage.length).toBe(0);
  });

  it('requires an explicit retry if the initial session request fails', async () => {
    let checks = 0;
    mockApi((path) => {
      if (path === '/api/v1/auth/me' && ++checks === 1)
        return Promise.reject(new TypeError('offline'));
      return undefined;
    });
    render(<App />);
    await screen.findByRole('button', { name: '重试登录检查' });
    expect(screen.queryByLabelText('日记内容')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '重试登录检查' }));
    await waitFor(() =>
      expect(screen.getByLabelText('日记内容')).toBeInTheDocument(),
    );
  });
});
