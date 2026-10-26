import { useCallback, useEffect, useRef, useState } from 'react';

import { getSession, logout } from '../api/auth';
import type { Session } from '../api/auth';
import { errorMessage, isUnauthorized } from '../api/client';
import { emptyDraft, hasUnsavedDraft, todayIn } from '../journal/draft';
import type { Draft } from '../journal/draft';
import { JournalWorkspace } from '../journal/JournalWorkspace';
import { CalendarWorkspace } from '../calendar/CalendarWorkspace';
import { ArchiveWorkspace } from '../search/ArchiveWorkspace';
import { emptySearchForm } from '../search/form';
import { TrashWorkspace } from '../trash/TrashWorkspace';
import { LoginForm } from './LoginForm';
import { AccountWorkspace } from './AccountWorkspace';
import { TagsWorkspace } from '../tags/TagsWorkspace';

export function AuthGate() {
  const [session, setSession] = useState<Session | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [check, setCheck] = useState(0);
  const [error, setError] = useState('');
  const [expired, setExpired] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [writeBusy, setWriteBusy] = useState(false);
  const [revalidating, setRevalidating] = useState(false);
  const [view, setView] = useState<
    'journal' | 'calendar' | 'archive' | 'trash' | 'account' | 'tags'
  >('journal');
  const [calendarDate, setCalendarDate] = useState<string | null>(null);
  const [searchForm, setSearchForm] = useState(emptySearchForm);
  const [journalRefresh, setJournalRefresh] = useState(0);
  const [securityUncertain, setSecurityUncertain] = useState(false);
  const ownerId = useRef<string | null>(null);
  const refreshCatalogue = useCallback(
    () => setJournalRefresh((value) => value + 1),
    [],
  );

  useEffect(() => {
    const controller = new AbortController();
    void getSession(controller.signal)
      .then((current) => {
        if (controller.signal.aborted) return;
        ownerId.current = current.user.id;
        setSession(current);
        setDraft(emptyDraft(current.user.timezone));
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted && !isUnauthorized(cause))
          setError(errorMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [check]);

  useEffect(() => {
    if (!hasUnsavedDraft(draft)) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [draft]);

  function acceptLogin(current: Session) {
    if (ownerId.current !== current.user.id || !draft) {
      setDraft(emptyDraft(current.user.timezone));
      setCalendarDate(null);
      setSearchForm(emptySearchForm);
      setView('journal');
    }
    ownerId.current = current.user.id;
    setSession(current);
    setSecurityUncertain(false);
    setExpired(false);
    setError('');
  }

  const expire = useCallback(() => {
    setSession(null);
    setExpired(true);
    setWriteBusy(false);
    setError('');
  }, []);

  async function revalidateSession() {
    if (revalidating || signingOut || writeBusy) return;
    setRevalidating(true);
    setError('');
    try {
      const current = await getSession();
      acceptLogin(current);
    } catch (cause) {
      if (isUnauthorized(cause)) expire();
      else setError(errorMessage(cause));
    } finally {
      setRevalidating(false);
    }
  }

  async function signOut() {
    if (!session || signingOut || writeBusy) return;
    if (
      hasUnsavedDraft(draft) &&
      !window.confirm('有未保存的草稿。退出会清空本页草稿，确认退出吗？')
    )
      return;
    setSigningOut(true);
    setError('');
    try {
      await logout(session.csrf_token);
    } catch (cause) {
      if (!isUnauthorized(cause)) {
        setError(`退出尚未确认。${errorMessage(cause)}`);
        return;
      }
    } finally {
      setSigningOut(false);
    }
    setSession(null);
    setDraft(null);
    setSecurityUncertain(false);
    ownerId.current = null;
    setExpired(false);
    setCalendarDate(null);
    setSearchForm(emptySearchForm);
    setView('journal');
  }

  if (loading)
    return (
      <p className="state-message" role="status">
        正在确认登录状态…
      </p>
    );
  if (!session) {
    return (
      <>
        {expired && (
          <p className="notice" role="alert">
            登录已失效。
            {hasUnsavedDraft(draft)
              ? '未保存草稿仅在当前页面内存中保留，重新登录后可继续。请勿刷新或关闭页面。'
              : '请重新登录。'}
          </p>
        )}
        {error ? (
          <section className="state-message">
            <p role="alert">{error}</p>
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                setLoading(true);
                setError('');
                setCheck((value) => value + 1);
              }}
            >
              重试登录检查
            </button>
          </section>
        ) : (
          <LoginForm onLogin={acceptLogin} />
        )}
      </>
    );
  }

  return (
    <>
      <div className="account-bar">
        <span>
          {session.user.username}{' '}
          <span className="small-note">· {session.user.timezone}</span>
        </span>
        <div>
          <button
            type="button"
            className="text-button"
            aria-current={view === 'account' ? 'page' : undefined}
            disabled={signingOut || writeBusy || revalidating}
            onClick={() => setView('account')}
          >
            账户
          </button>{' '}
          <button
            type="button"
            className="text-button"
            disabled={signingOut || writeBusy || revalidating}
            onClick={() => void revalidateSession()}
          >
            {revalidating ? '正在验证…' : '重新验证登录'}
          </button>{' '}
          <button
            type="button"
            className="text-button"
            disabled={signingOut || writeBusy || revalidating}
            onClick={() => void signOut()}
          >
            {signingOut ? '正在退出…' : '退出登录'}
          </button>
        </div>
      </div>
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      <nav className="workspace-navigation" aria-label="主导航">
        <button
          type="button"
          className={`nav-item ${view === 'journal' ? 'selected' : ''}`}
          aria-current={view === 'journal' ? 'page' : undefined}
          disabled={signingOut || revalidating || writeBusy}
          onClick={() => setView('journal')}
        >
          日记
        </button>
        <button
          type="button"
          className={`nav-item ${view === 'calendar' ? 'selected' : ''}`}
          aria-current={view === 'calendar' ? 'page' : undefined}
          disabled={signingOut || revalidating || writeBusy}
          onClick={() => setView('calendar')}
        >
          日历
        </button>
        <button
          type="button"
          className={`nav-item ${view === 'archive' ? 'selected' : ''}`}
          aria-current={view === 'archive' ? 'page' : undefined}
          disabled={signingOut || revalidating || writeBusy}
          onClick={() => setView('archive')}
        >
          归档
        </button>
        <button
          type="button"
          className={`nav-item ${view === 'trash' ? 'selected' : ''}`}
          aria-current={view === 'trash' ? 'page' : undefined}
          disabled={signingOut || revalidating || writeBusy}
          onClick={() => setView('trash')}
        >
          回收站
        </button>
        <button
          type="button"
          className={`nav-item ${view === 'tags' ? 'selected' : ''}`}
          aria-current={view === 'tags' ? 'page' : undefined}
          disabled={signingOut || revalidating || writeBusy}
          onClick={() => setView('tags')}
        >
          标签管理
        </button>
      </nav>
      {draft && (
        <div hidden={view !== 'journal'}>
          <JournalWorkspace
            session={session}
            draft={draft}
            onDraft={setDraft}
            onExpired={expire}
            onBusy={setWriteBusy}
            refreshVersion={journalRefresh}
            disabled={signingOut || revalidating || view !== 'journal'}
          />
        </div>
      )}
      {view === 'calendar' && (
        <CalendarWorkspace
          date={calendarDate ?? todayIn(session.user.timezone)}
          timezone={session.user.timezone}
          onDate={setCalendarDate}
          onExpired={expire}
          disabled={signingOut || revalidating}
        />
      )}
      {view === 'archive' && (
        <ArchiveWorkspace
          form={searchForm}
          onForm={setSearchForm}
          csrfToken={session.csrf_token}
          onExpired={expire}
          disabled={signingOut || revalidating}
        />
      )}
      {view === 'trash' && (
        <TrashWorkspace
          csrfToken={session.csrf_token}
          timezone={session.user.timezone}
          onExpired={expire}
          onBusy={setWriteBusy}
          onRestored={() => setJournalRefresh((value) => value + 1)}
          disabled={signingOut || revalidating}
        />
      )}
      {view === 'account' && (
        <AccountWorkspace
          session={session}
          disabled={signingOut || revalidating}
          uncertain={securityUncertain}
          onSession={acceptLogin}
          onUncertain={() => setSecurityUncertain(true)}
          onExpired={expire}
          onBusy={setWriteBusy}
        />
      )}
      {view === 'tags' && (
        <TagsWorkspace
          csrfToken={session.csrf_token}
          onExpired={expire}
          onBusy={setWriteBusy}
          onCatalogue={refreshCatalogue}
          disabled={signingOut || revalidating}
        />
      )}
    </>
  );
}
