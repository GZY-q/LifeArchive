import { useEffect, useRef, useState } from 'react';

import { getDay } from '../api/calendar';
import { errorMessage, isUnauthorized } from '../api/client';
import type { Entry } from '../api/journal';
import { TagBadges } from '../journal/TagBadges';

type Props = { date: string; disabled: boolean; onExpired: () => void };

/** Mounted with a date key, so cursors and requests never migrate to another day. */
export function DayEntries({ date, disabled, onExpired }: Props) {
  const [items, setItems] = useState<Entry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const nextRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void getDay(date, undefined, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setItems(result.entries.items);
        setCursor(result.entries.next_cursor);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(cause)) onExpired();
        else setError(errorMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => {
      controller.abort();
      nextRequest.current?.abort();
    };
  }, [date, retry, onExpired]);

  async function more() {
    if (!cursor || busy || disabled) return;
    const controller = new AbortController();
    nextRequest.current = controller;
    setBusy(true);
    setError('');
    try {
      const result = await getDay(date, cursor, controller.signal);
      if (controller.signal.aborted) return;
      setItems((current) => [
        ...current,
        ...result.entries.items.filter(
          (entry) => !current.some((old) => old.id === entry.id),
        ),
      ]);
      setCursor(result.entries.next_cursor);
    } catch (cause) {
      if (controller.signal.aborted) return;
      if (isUnauthorized(cause)) onExpired();
      else setError(errorMessage(cause));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <section className="day-detail" aria-label={`${date} 的日记`}>
      <div className="section-heading">
        <h2>
          <time dateTime={date}>{date}</time> 的记录
        </h2>
      </div>
      {items.map((entry) => (
        <article
          className="day-entry paper-card"
          aria-label={`${date} 的日记，版本 ${entry.revision}`}
          key={entry.id}
        >
          <p className="small-note">版本 {entry.revision}</p>
          <pre className="markdown-text">{entry.content_md}</pre>
          <TagBadges tags={entry.tags} />
        </article>
      ))}
      {busy && (
        <p className="state-message" role="status">
          正在读取这一天的日记…
        </p>
      )}
      {!busy && !error && !items.length && (
        <p className="empty-state">这一天还没有日记。</p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {error && !cursor && (
        <button
          className="secondary-button"
          type="button"
          disabled={busy || disabled}
          onClick={() => {
            setBusy(true);
            setError('');
            setRetry((value) => value + 1);
          }}
        >
          重试读取这一天
        </button>
      )}
      {cursor && (
        <button
          className="secondary-button load-more"
          type="button"
          disabled={busy || disabled}
          onClick={() => void more()}
        >
          加载这一天的更多日记
        </button>
      )}
    </section>
  );
}
