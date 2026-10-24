import { invalidResponse, isRecord, request } from './client';

export type Owner = { id: string; username: string; timezone: string };
export type Session = { user: Owner; csrf_token: string };

function sessionFrom(value: unknown): Session {
  if (
    !isRecord(value) ||
    !isRecord(value.user) ||
    typeof value.user.id !== 'string' ||
    typeof value.user.username !== 'string' ||
    typeof value.user.timezone !== 'string' ||
    typeof value.csrf_token !== 'string' ||
    !value.csrf_token
  )
    return invalidResponse();
  return {
    user: {
      id: value.user.id,
      username: value.user.username,
      timezone: value.user.timezone,
    },
    csrf_token: value.csrf_token,
  };
}

export async function getSession(signal?: AbortSignal): Promise<Session> {
  return sessionFrom(await request('/auth/me', { signal }));
}

export async function login(
  username: string,
  password: string,
): Promise<Session> {
  return sessionFrom(
    await request('/auth/login', {
      method: 'POST',
      body: { username, password },
    }),
  );
}

export async function logout(csrfToken: string): Promise<void> {
  await request('/auth/logout', { method: 'POST', csrfToken });
}
