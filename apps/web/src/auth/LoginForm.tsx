import { useState } from 'react';
import type { FormEvent } from 'react';

import { login } from '../api/auth';
import type { Session } from '../api/auth';
import { ApiError, errorMessage } from '../api/client';

export function LoginForm({
  onLogin,
}: {
  onLogin: (session: Session) => void;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      onLogin(await login(username, password));
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 401
          ? '用户名或密码不正确。'
          : errorMessage(cause),
      );
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  return (
    <section className="login-panel" aria-labelledby="login-title">
      <h1 id="login-title">欢迎回来。</h1>
      <p className="muted">登录后，继续记录属于你的日子。</p>
      <form className="login-form" onSubmit={(event) => void submit(event)}>
        <label htmlFor="username">用户名</label>
        <input
          id="username"
          name="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
          required
          disabled={busy}
        />
        <label htmlFor="password">密码</label>
        <input
          id="password"
          name="password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          required
          disabled={busy}
        />
        {error && (
          <p className="error-message" role="alert">
            {error}
          </p>
        )}
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? '正在登录…' : '登录'}
        </button>
      </form>
      <p className="small-note">这是私人档案，仅限已配置的所有者登录。</p>
    </section>
  );
}
