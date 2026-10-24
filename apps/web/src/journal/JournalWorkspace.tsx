import { useEffect, useState } from 'react';

import type { Session } from '../api/auth';
import { ApiError, errorMessage, isUnauthorized } from '../api/client';
import { deleteEntry, listEntries } from '../api/journal';
import type { Entry } from '../api/journal';
import { emptyDraft, hasUnsavedDraft } from './draft';
import type { Draft } from './draft';
import { EntryCard } from './EntryCard';
import { EntryForm } from './EntryForm';

type Props = {
  session: Session;
  draft: Draft;
  onDraft: (draft: Draft) => void;
  onExpired: () => void;
  onBusy: (busy: boolean) => void;
  disabled: boolean;
};

export function JournalWorkspace({
  session,
  draft,
  onDraft,
  onExpired,
  onBusy,
  disabled,
}: Props) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [formKey, setFormKey] = useState(0);
  const [saved, setSaved] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    void listEntries(undefined, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setEntries(result.items);
        setCursor(result.next_cursor);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(cause)) onExpired();
        else setListError(errorMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refresh, onExpired]);

  function refreshList() {
    setLoading(true);
    setListError('');
    setRefresh((current) => current + 1);
  }

  async function loadMore() {
    if (!cursor || loading) return;
    setLoading(true);
    setListError('');
    try {
      const result = await listEntries(cursor);
      setEntries((current) => [
        ...current,
        ...result.items.filter(
          (item) => !current.some((old) => old.id === item.id),
        ),
      ]);
      setCursor(result.next_cursor);
    } catch (cause) {
      if (isUnauthorized(cause)) onExpired();
      else setListError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  }

  function changeDraft(entry: Entry | null) {
    if (busy || disabled) return;
    if (draft.pendingCreate) {
      setActionError('请先重试并确认当前日记的保存结果，再切换编辑。');
      return;
    }
    if (
      hasUnsavedDraft(draft) &&
      !window.confirm('当前有未保存的内容。确认放弃这些修改吗？')
    )
      return;
    onDraft(
      entry
        ? {
            content_md: entry.content_md,
            entry_date: entry.entry_date,
            original: entry,
            pendingCreate: null,
          }
        : emptyDraft(session.user.timezone),
    );
    setFormKey((value) => value + 1);
    setSaved('');
    setActionError('');
    document
      .getElementById('composer-title')
      ?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }

  function writing(value: boolean) {
    setBusy(value);
    onBusy(value);
  }

  async function remove(entry: Entry) {
    if (busy || disabled) return;
    if (
      !window.confirm(
        `确认删除 ${entry.entry_date} 的这篇日记吗？它将不再显示在列表中。`,
      )
    )
      return;
    writing(true);
    setActionError('');
    try {
      await deleteEntry(entry, session.csrf_token);
      setEntries((current) => current.filter((item) => item.id !== entry.id));
      setSaved('日记已删除。');
      refreshList();
    } catch (cause) {
      if (isUnauthorized(cause)) onExpired();
      else if (cause instanceof ApiError && cause.status === 409) {
        setActionError(
          '这篇日记已有修改，尚未删除。请刷新列表、核对内容后再操作。',
        );
      } else setActionError(errorMessage(cause));
    } finally {
      writing(false);
    }
  }

  return (
    <div id="journal" className="journal-workspace">
      <EntryForm
        key={formKey}
        draft={draft}
        csrfToken={session.csrf_token}
        disabled={disabled || busy}
        onDraft={onDraft}
        onExpired={onExpired}
        onBusy={writing}
        onCancel={() => changeDraft(null)}
        onSaved={() => {
          onDraft(emptyDraft(session.user.timezone));
          setFormKey((value) => value + 1);
          setSaved('日记已保存。');
          refreshList();
        }}
      />
      {saved && (
        <p className="success-message" role="status">
          {saved}
        </p>
      )}
      <section aria-labelledby="entries-title" className="entries-section">
        <div className="section-heading">
          <h2 id="entries-title">日子，慢慢积累</h2>
          <button
            type="button"
            className="text-button"
            disabled={loading || busy || disabled}
            onClick={refreshList}
          >
            刷新列表
          </button>
        </div>
        {actionError && (
          <p className="error-message" role="alert">
            {actionError}
          </p>
        )}
        {entries.map((entry) => (
          <EntryCard
            key={`${entry.id}:${entry.revision}`}
            entry={entry}
            disabled={busy || disabled || draft.original?.id === entry.id}
            onEdit={changeDraft}
            onDelete={(item) => void remove(item)}
            onExpired={onExpired}
          />
        ))}
        {loading && (
          <p className="state-message" role="status">
            正在读取日记…
          </p>
        )}
        {!loading && !listError && !entries.length && (
          <div className="empty-state">
            <h3>还没有记录</h3>
            <p>从一件小事开始，写下你的第一篇日记。</p>
          </div>
        )}
        {listError && (
          <p className="error-message" role="alert">
            {listError}
          </p>
        )}
        {listError && !cursor && (
          <button
            type="button"
            className="secondary-button"
            disabled={loading}
            onClick={refreshList}
          >
            重试读取日记
          </button>
        )}
        {cursor && (
          <button
            type="button"
            className="secondary-button load-more"
            disabled={loading || disabled}
            onClick={() => void loadMore()}
          >
            加载更多日记
          </button>
        )}
      </section>
    </div>
  );
}
