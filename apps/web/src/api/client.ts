export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  csrfToken?: string;
  signal?: AbortSignal;
};

export async function request(
  path: string,
  { method = 'GET', body, csrfToken, signal }: RequestOptions = {},
): Promise<unknown> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener('abort', cancel, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = window.setTimeout(cancel, 15_000);
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (method !== 'GET') headers['X-LifeArchive-Request'] = '1';
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken;

  try {
    const response = await fetch(`/api/v1${path}`, {
      method,
      body: body === undefined ? undefined : JSON.stringify(body),
      headers,
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    });
    if (!response.ok) {
      let code = 'request_failed';
      try {
        const data: unknown = await response.json();
        if (
          isRecord(data) &&
          isRecord(data.detail) &&
          typeof data.detail.code === 'string'
        ) {
          code = data.detail.code;
        }
      } catch {
        // HTTP status remains authoritative even for an HTML proxy error.
      }
      throw new ApiError(response.status, code);
    }
    if (response.status === 204) return undefined;
    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      0,
      controller.signal.aborted ? 'request_aborted' : 'network_error',
    );
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function invalidResponse(): never {
  throw new ApiError(0, 'invalid_response');
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403)
      return '安全校验未通过，请重新验证登录后重试。当前草稿仍保留。';
    if (error.status === 404) return '这篇日记已不可用，请刷新列表。';
    if (error.status === 422) return '内容或日期格式不符合要求，请检查后重试。';
    if (error.status === 429) return '尝试过于频繁，请稍后重试。';
  }
  return '暂时无法完成请求，请检查连接后重试。';
}
