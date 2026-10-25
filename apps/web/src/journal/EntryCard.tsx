import { useState } from 'react';

import type { Entry } from '../api/journal';
import { RevisionHistory } from './RevisionHistory';
import { TagBadges } from './TagBadges';

export function EntryCard({
  entry,
  disabled,
  onEdit,
  onDelete,
  onExpired,
}: {
  entry: Entry;
  disabled: boolean;
  onEdit: (entry: Entry) => void;
  onDelete: (entry: Entry) => void;
  onExpired: () => void;
}) {
  const [historyOpen, setHistoryOpen] = useState(false);
  return (
    <article
      className="entry-card paper-card"
      aria-label={`${entry.entry_date} 的日记`}
    >
      <div className="entry-meta">
        <time dateTime={entry.entry_date}>{entry.entry_date}</time>
        <span className="small-note">版本 {entry.revision}</span>
      </div>
      <pre className="markdown-text">{entry.content_md}</pre>
      <TagBadges tags={entry.tags} />
      <div className="entry-actions">
        <button
          type="button"
          className="text-button"
          disabled={disabled}
          onClick={() => onEdit(entry)}
        >
          编辑
        </button>
        <button
          type="button"
          className="text-button"
          disabled={disabled}
          aria-expanded={historyOpen}
          onClick={() => setHistoryOpen((open) => !open)}
        >
          {historyOpen ? '收起历史' : '修订历史'}
        </button>
        <button
          type="button"
          className="text-button danger-button"
          disabled={disabled}
          onClick={() => onDelete(entry)}
        >
          删除
        </button>
      </div>
      {historyOpen && (
        <RevisionHistory entryId={entry.id} onExpired={onExpired} />
      )}
    </article>
  );
}
