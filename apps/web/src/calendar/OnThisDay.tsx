import { useEffect, useRef, useState } from 'react';

import { MarkdownContent } from '../components/MarkdownContent';

import { getOnThisDay } from '../api/calendar';
import { errorMessage, isUnauthorized } from '../api/client';
import type { Entry } from '../api/journal';
import { TagBadges } from '../journal/TagBadges';
import { AssetGallery } from '../journal/AssetGallery';
import { PinnedBadge } from '../journal/PinnedBadge';

type Props = {
  date: string;
  refresh: number;
  disabled: boolean;
  onExpired: () => void;
};

export function OnThisDay({ date, refresh, disabled, onExpired }: Props) {
  const [expanded, setExpanded] = useState(false);
  return (
    <section className="day-detail" aria-label="往年这一天">
      <div className="section-heading">
        <h2>往年这一天</h2>
        <button
          className="secondary-button"
          type="button"
          aria-expanded={expanded}
          aria-controls="on-this-day-results"
          disabled={disabled}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? '收起往年这一天' : '展开往年这一天'}
        </button>
      </div>
      <p className="small-note">
        查看 {date} 以前年度同月同日的记录；2 月 29 日仅匹配往年的闰日。
      </p>
      <div id="on-this-day-results">
        {expanded && (
          <PastEntries
            key={`${date}:${refresh}`}
            date={date}
            disabled={disabled}
            onExpired={onExpired}
          />
        )}
      </div>
    </section>
  );
}

/** Date/refresh keys reset paging; closing or leaving the view aborts all reads. */
function PastEntries({ date, disabled, onExpired }: Omit<Props, 'refresh'>) {
  const [items, setItems] = useState<Entry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const nextRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void getOnThisDay(date, undefined, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        setItems(page.entries.items);
        setCursor(page.entries.next_cursor);
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
      const page = await getOnThisDay(date, cursor, controller.signal);
      if (controller.signal.aborted) return;
      setItems((current) => [
        ...current,
        ...page.entries.items.filter(
          (entry) => !current.some((old) => old.id === entry.id),
        ),
      ]);
      setCursor(page.entries.next_cursor);
    } catch (cause) {
      if (controller.signal.aborted) return;
      if (isUnauthorized(cause)) onExpired();
      else setError(errorMessage(cause));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  function retryRead() {
    if (busy || disabled) return;
    if (cursor) void more();
    else {
      setBusy(true);
      setError('');
      setRetry((value) => value + 1);
    }
  }

  return (
    <div aria-busy={busy}>
      {items.map((entry) => (
        <article
          className="on-this-day-entry day-entry paper-card"
          key={entry.id}
        >
          <p className="small-note">
            <time dateTime={entry.entry_date}>{entry.entry_date}</time>
            {' · '}版本 {entry.revision}
          </p>
          <PinnedBadge isPinned={entry.is_pinned} />
          <MarkdownContent
            content={entry.content_md}
            label={`${entry.entry_date} 往年日记原文与预览`}
            disabled={disabled}
          />
          <TagBadges tags={entry.tags} />
          <AssetGallery assets={entry.assets} onExpired={onExpired} />
        </article>
      ))}
      {busy && (
        <p className="state-message" role="status">
          正在读取往年日记…
        </p>
      )}
      {!busy && !error && !items.length && (
        <p className="empty-state">往年这一天还没有日记。</p>
      )}
      {error && (
        <div>
          <p className="error-message" role="alert">
            {error}
          </p>
          <button
            className="secondary-button"
            type="button"
            disabled={busy || disabled}
            onClick={retryRead}
          >
            重试读取往年日记
          </button>
        </div>
      )}
      {cursor && !error && (
        <button
          className="secondary-button load-more"
          type="button"
          disabled={busy || disabled}
          onClick={() => void more()}
        >
          加载往年更多日记
        </button>
      )}
    </div>
  );
}
