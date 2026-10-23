import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { App } from './App';

function stubResponse(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('foundation home', () => {
  it('shows the initial loading state and keeps future navigation disabled', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})));

    render(<App />);

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      '把日子，慢慢留下。',
    );
    expect(screen.getByRole('link', { name: '首页' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(
      screen.getByRole('button', { name: /日记\s*待开放/ }),
    ).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('正在检查连接');
    expect(screen.getByRole('button', { name: '检查连接' })).toBeDisabled();
  });

  it('checks the same-origin health endpoint and reports a healthy service', async () => {
    const fetchMock = stubResponse({ status: 'ok' });

    render(<App />);

    expect(await screen.findByText('服务已连接')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health', {
      signal: expect.any(AbortSignal),
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
  });

  it('reports HTTP errors even if the body says ok', async () => {
    stubResponse({ status: 'ok' }, 503);

    render(<App />);

    expect(await screen.findByText('暂时无法连接服务')).toBeInTheDocument();
  });

  it.each([null, {}, { status: 'unhealthy' }, 'ok'])(
    'rejects an invalid health payload: %j',
    async (payload) => {
      stubResponse(payload);

      render(<App />);

      expect(await screen.findByText('暂时无法连接服务')).toBeInTheDocument();
    },
  );

  it('rejects non-JSON responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>Unavailable</html>')),
    );

    render(<App />);

    expect(await screen.findByText('暂时无法连接服务')).toBeInTheDocument();
  });

  it('allows a failed network request to be retried', async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' })));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    expect(await screen.findByText('暂时无法连接服务')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重新检查连接' }));

    expect(await screen.findByText('服务已连接')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('stops waiting after eight seconds and allows another attempt', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, options: RequestInit) => {
        return new Promise<Response>((_resolve, reject) => {
          options.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        });
      }),
    );

    render(<App />);
    await act(() => vi.advanceTimersByTimeAsync(8_000));

    expect(screen.getByRole('status')).toHaveTextContent('暂时无法连接服务');
    expect(screen.getByRole('button', { name: '重新检查连接' })).toBeEnabled();
  });
});
