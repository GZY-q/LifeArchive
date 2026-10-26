import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';

import { changePassword, revokeOtherSessions } from '../api/auth';
import type { Session } from '../api/auth';
import { ApiError, errorMessage, isUnauthorized } from '../api/client';

type Props = {
  session: Session;
  disabled: boolean;
  uncertain: boolean;
  onSession: (session: Session) => void;
  onUncertain: () => void;
  onExpired: () => void;
  onBusy: (busy: boolean) => void;
};

function accountError(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 403 && cause.code === 'invalid_current_password')
      return '当前密码不正确，请重新输入。';
    if (cause.status === 422)
      return cause.code === 'password_unchanged'
        ? '新密码不能与当前密码相同。'
        : '请检查密码格式，新密码须为 15–1024 个字符。';
  }
  return errorMessage(cause);
}

export function AccountWorkspace({
  session,
  disabled,
  uncertain,
  onSession,
  onUncertain,
  onExpired,
  onBusy,
}: Props) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const writing = useRef(false);
  const mounted = useRef(false);
  const locked = disabled || busy || uncertain;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  function clearPasswords() {
    setCurrent('');
    setNext('');
    setConfirmation('');
  }

  async function perform(action: 'password' | 'revoke') {
    if (disabled || uncertain || writing.current) return;
    setError('');
    setNotice('');
    const currentLength = Array.from(current).length;
    const nextLength = Array.from(next).length;
    if (currentLength < 1 || currentLength > 1024) {
      clearPasswords();
      setError('请输入 1–1024 个字符的当前密码。');
      return;
    }
    if (
      action === 'password' &&
      (nextLength < 15 ||
        nextLength > 1024 ||
        !next.trim() ||
        next.includes('\0'))
    ) {
      clearPasswords();
      setError('新密码须为 15–1024 个字符，不能仅为空白或包含空字符。');
      return;
    }
    if (action === 'password' && next !== confirmation) {
      clearPasswords();
      setError('两次输入的新密码不一致，请重新输入。');
      return;
    }
    writing.current = true;
    setBusy(true);
    onBusy(true);
    try {
      const updated =
        action === 'password'
          ? await changePassword(current, next, session.csrf_token)
          : await revokeOtherSessions(current, session.csrf_token);
      if (!mounted.current) return;
      onSession(updated);
      setNotice(
        action === 'password'
          ? '密码已更新，其他会话已退出；本页草稿仍保留。'
          : '其他会话已退出，当前页面可继续使用。',
      );
    } catch (cause) {
      if (!mounted.current) return;
      if (isUnauthorized(cause)) onExpired();
      else if (
        cause instanceof ApiError &&
        (cause.status === 0 || cause.status >= 500)
      ) {
        onUncertain();
      } else setError(accountError(cause));
    } finally {
      writing.current = false;
      if (mounted.current) {
        clearPasswords();
        setBusy(false);
        onBusy(false);
      }
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void perform('password');
  }

  return (
    <section
      className="paper-card account-workspace"
      aria-labelledby="account-title"
    >
      <h2 id="account-title">账户安全</h2>
      <p className="small-note">
        修改密码或退出其他会话都需要验证当前密码。成功后，其他浏览器需要重新登录，当前页面继续保留日记草稿。
      </p>
      {uncertain && (
        <p className="notice" role="alert">
          操作结果尚未确认，未自动重试。请先使用“重新验证登录”核对；若登录失效，请尝试用新密码重新登录。日记草稿仍保留，请勿刷新页面。
        </p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="success-message" role="status">
          {notice}
        </p>
      )}
      <form className="login-form" onSubmit={submit} noValidate>
        <fieldset className="account-fields" disabled={locked}>
          <legend className="visually-hidden">账户密码</legend>
          <label htmlFor="account-current-password">当前密码</label>
          <input
            id="account-current-password"
            name="current_password"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
          />
          <label htmlFor="account-new-password">新密码</label>
          <input
            id="account-new-password"
            name="new_password"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(event) => setNext(event.target.value)}
            aria-describedby="new-password-help"
          />
          <p id="new-password-help" className="small-note">
            15–1024 个字符，保留空格和原始字符。
          </p>
          <label htmlFor="account-confirm-password">确认新密码</label>
          <input
            id="account-confirm-password"
            name="confirm_password"
            type="password"
            autoComplete="new-password"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
          />
          <button className="primary-button" type="submit" disabled={locked}>
            {busy ? '正在处理…' : '保存新密码'}
          </button>
          <div className="account-session-action">
            <h3>其他会话</h3>
            <p className="small-note">
              只需填写当前密码，即可退出其他浏览器的登录，不修改密码。
            </p>
            <button
              type="button"
              className="secondary-button"
              disabled={locked}
              onClick={() => void perform('revoke')}
            >
              退出其他会话
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  );
}
