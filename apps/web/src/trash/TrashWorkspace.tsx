import { useEffect, useRef, useState } from 'react';

import { ApiError, errorMessage, isUnauthorized } from '../api/client';
import { listTrash, restoreEntry } from '../api/trash';
import type { TrashEntry } from '../api/trash';
import { TagBadges } from '../journal/TagBadges';

type Props = {
  csrfToken: string;
  timezone: string;
  disabled: boolean;
  onExpired: () => void;
  onBusy: (busy: boolean) => void;
  onRestored: () => void;
};

export function TrashWorkspace({
  csrfToken,
  timezone,
  disabled,
  onExpired,
  onBusy,
  onRestored,
}: Props) {
  const [items, setItems] = useState<TrashEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [refresh, setRefresh] = useState(0);
  const firstRequest = useRef<AbortController | null>(null);
  const nextRequest = useRef<AbortController | null>(null);
  const writing = useRef(false);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    firstRequest.current = controller;
    void listTrash(undefined, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        setItems(page.items);
        setCursor(page.next_cursor);
        setBlocked([]);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(cause)) onExpired();
        else setError(errorMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      controller.abort();
      nextRequest.current?.abort();
    };
  }, [refresh, onExpired]);

  function reload() {
    if (writing.current || disabled) return;
    firstRequest.current?.abort();
    nextRequest.current?.abort();
    setLoading(true);
    setError('');
    setRefresh((value) => value + 1);
  }

  async function more() {
    if (!cursor || loading || writing.current || disabled) return;
    nextRequest.current?.abort();
    const controller = new AbortController();
    nextRequest.current = controller;
    setLoading(true);
    setError('');
    try {
      const page = await listTrash(cursor, controller.signal);
      if (controller.signal.aborted) return;
      setItems((current) => [
        ...current,
        ...page.items.filter(
          (item) => !current.some((old) => old.id === item.id),
        ),
      ]);
      setCursor(page.next_cursor);
    } catch (cause) {
      if (controller.signal.aborted) return;
      if (isUnauthorized(cause)) onExpired();
      else setError(errorMessage(cause));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  async function restore(entry: TrashEntry) {
    if (writing.current || loading || disabled || blocked.includes(entry.id))
      return;
    writing.current = true;
    setRestoring(entry.id);
    setError('');
    setNotice('');
    onBusy(true);
    try {
      await restoreEntry(entry, csrfToken);
      if (!mounted.current) return;
      setItems((current) => current.filter((item) => item.id !== entry.id));
      setNotice('日记已恢复，可回到日记列表查看。');
      onRestored();
    } catch (cause) {
      if (!mounted.current) return;
      if (isUnauthorized(cause)) onExpired();
      else {
        setBlocked((current) => [...current, entry.id]);
        setError(
          cause instanceof ApiError && cause.status === 409
            ? '这篇日记的状态已有变化，请刷新回收站后核对。'
            : cause instanceof ApiError && cause.status === 0
              ? '恢复结果尚未确认。请刷新回收站核对，再决定是否重试。'
              : `${errorMessage(cause)} 请刷新回收站后核对。`,
        );
      }
    } finally {
      writing.current = false;
      if (mounted.current) setRestoring(null);
      onBusy(false);
    }
  }

  return (
    <section className="trash-workspace" aria-labelledby="trash-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">KEEP WHAT MATTERS</p>
          <h2 id="trash-title">回收站</h2>
        </div>
        <button
          type="button"
          className="text-button"
          disabled={disabled || loading || restoring !== null}
          onClick={reload}
        >
          刷新回收站
        </button>
      </div>
      <p className="small-note">
        已删除的日记保留在这里，恢复后回到原来的日记日期。
      </p>
      {notice && (
        <p className="success-message" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {items.map((entry) => (
        <article
          key={entry.id}
          className="entry-card paper-card"
          aria-label={`${entry.entry_date} 的已删除日记`}
        >
          <div className="entry-meta">
            <time dateTime={entry.entry_date}>{entry.entry_date}</time>
            <span className="small-note">版本 {entry.revision}</span>
          </div>
          <p className="small-note">
            删除于{' '}
            <time dateTime={entry.deleted_at}>
              {new Intl.DateTimeFormat('zh-CN', {
                timeZone: timezone,
                dateStyle: 'medium',
                timeStyle: 'short',
              }).format(new Date(entry.deleted_at))}
            </time>
          </p>
          <pre className="markdown-text">{entry.content_md}</pre>
          <TagBadges tags={entry.tags} />
          <div className="entry-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={
                disabled ||
                loading ||
                restoring !== null ||
                blocked.includes(entry.id)
              }
              onClick={() => void restore(entry)}
            >
              {restoring === entry.id ? '正在恢复…' : '恢复日记'}
            </button>
          </div>
        </article>
      ))}
      {loading && (
        <p className="state-message" role="status">
          正在读取回收站…
        </p>
      )}
      {!loading && !error && !items.length && (
        <div className="empty-state">
          <h3>回收站是空的</h3>
          <p>删除的日记会显示在这里。</p>
        </div>
      )}
      {cursor && (
        <button
          type="button"
          className="secondary-button load-more"
          disabled={disabled || loading || restoring !== null}
          onClick={() => void more()}
        >
          加载更多已删除日记
        </button>
      )}
    </section>
  );
}
