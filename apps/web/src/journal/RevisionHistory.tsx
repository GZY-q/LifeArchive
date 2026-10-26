import { useEffect, useState } from 'react';

import { MarkdownContent } from '../components/MarkdownContent';

import { errorMessage, isUnauthorized } from '../api/client';
import { listRevisions } from '../api/journal';
import type { EntryRevision } from '../api/journal';
import { TagBadges } from './TagBadges';
import { AssetGallery } from './AssetGallery';
import { PinnedBadge } from './PinnedBadge';

export function RevisionHistory({
  entryId,
  onExpired,
}: {
  entryId: string;
  onExpired: () => void;
}) {
  const [items, setItems] = useState<EntryRevision[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void listRevisions(entryId, undefined, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setItems(result.items);
        setCursor(result.next_cursor);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(cause)) onExpired();
        else setError(errorMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [entryId, retry, onExpired]);

  async function more() {
    if (cursor === null || busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await listRevisions(entryId, cursor);
      setItems((current) => [
        ...current,
        ...result.items.filter(
          (item) =>
            !current.some((previous) => previous.revision === item.revision),
        ),
      ]);
      setCursor(result.next_cursor);
    } catch (cause) {
      if (isUnauthorized(cause)) onExpired();
      else setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="revision-history" aria-label="修订历史">
      <h3>修订历史</h3>
      {items.map((revision) => (
        <article key={revision.revision} className="revision">
          <p className="small-note">
            版本 {revision.revision} · 日记日期 {revision.entry_date}
          </p>
          <PinnedBadge isPinned={revision.is_pinned} />
          <MarkdownContent
            content={revision.content_md}
            label={`修订 ${revision.revision} 原文与预览`}
          />
          <TagBadges tags={revision.tags} />
          <AssetGallery assets={revision.assets} onExpired={onExpired} />
        </article>
      ))}
      {busy && <p role="status">正在读取历史…</p>}
      {!busy && !error && !items.length && (
        <p className="small-note">暂无历史版本。</p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {!items.length && error && (
        <button
          type="button"
          className="secondary-button"
          onClick={() => {
            setBusy(true);
            setError('');
            setRetry((value) => value + 1);
          }}
        >
          重试读取历史
        </button>
      )}
      {cursor !== null && (
        <button
          type="button"
          className="secondary-button"
          disabled={busy}
          onClick={() => void more()}
        >
          加载更早版本
        </button>
      )}
    </section>
  );
}
