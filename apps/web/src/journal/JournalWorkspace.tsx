import { useEffect, useRef, useState } from 'react';

import type { Session } from '../api/auth';
import { ApiError, errorMessage, isUnauthorized } from '../api/client';
import { deleteEntry, listEntries, setEntryPinned } from '../api/journal';
import type { Entry } from '../api/journal';
import { listTags } from '../api/tags';
import type { Tag } from '../api/tags';
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
  refreshVersion?: number;
};

export function JournalWorkspace({
  session,
  draft,
  onDraft,
  onExpired,
  onBusy,
  disabled,
  refreshVersion = 0,
}: Props) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [requestLoading, setLoading] = useState(true);
  const [listFailure, setListError] = useState('');
  const [loadedVersion, setLoadedVersion] = useState(refreshVersion);
  const [actionError, setActionError] = useState('');
  const [pinBlocked, setPinBlocked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [formKey, setFormKey] = useState(0);
  const [saved, setSaved] = useState('');
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagsLoading, setTagsLoading] = useState(true);
  const [tagsError, setTagsError] = useState('');
  const [tagsRefresh, setTagsRefresh] = useState(0);
  const [filterTagId, setFilterTagId] = useState('');
  const nextRequest = useRef<AbortController | null>(null);
  const firstRequest = useRef<AbortController | null>(null);
  const loading = requestLoading || loadedVersion !== refreshVersion;
  const listError = loadedVersion === refreshVersion ? listFailure : '';

  useEffect(() => {
    const controller = new AbortController();
    void listTags(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted)
          setTags((current) =>
            [
              ...items,
              ...current.filter(
                (tag) => !items.some((item) => item.id === tag.id),
              ),
            ].sort((a, b) => a.name.localeCompare(b.name, 'zh-CN')),
          );
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(cause)) onExpired();
        else setTagsError(errorMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setTagsLoading(false);
      });
    return () => controller.abort();
  }, [tagsRefresh, onExpired]);

  useEffect(() => {
    const controller = new AbortController();
    firstRequest.current = controller;
    void listEntries(undefined, controller.signal, filterTagId)
      .then((result) => {
        if (controller.signal.aborted) return;
        setEntries(result.items);
        setPinBlocked([]);
        setCursor(result.next_cursor);
        setListError('');
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(cause)) onExpired();
        else {
          setCursor(null);
          setListError(errorMessage(cause));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoadedVersion(refreshVersion);
          setLoading(false);
        }
      });
    return () => {
      controller.abort();
      nextRequest.current?.abort();
    };
  }, [refresh, onExpired, filterTagId, refreshVersion]);

  function refreshList() {
    firstRequest.current?.abort();
    nextRequest.current?.abort();
    setLoading(true);
    setListError('');
    setActionError('');
    setRefresh((current) => current + 1);
  }

  async function loadMore() {
    if (!cursor || loading) return;
    const controller = new AbortController();
    nextRequest.current = controller;
    setLoading(true);
    setListError('');
    try {
      const result = await listEntries(cursor, controller.signal, filterTagId);
      if (controller.signal.aborted) return;
      setEntries((current) => [
        ...current,
        ...result.items.filter(
          (item) => !current.some((old) => old.id === item.id),
        ),
      ]);
      setCursor(result.next_cursor);
    } catch (cause) {
      if (controller.signal.aborted) return;
      if (isUnauthorized(cause)) onExpired();
      else setListError(errorMessage(cause));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
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
            tag_ids: entry.tags.map((tag) => tag.id),
            asset_ids: entry.assets.map((asset) => asset.id),
            attachments: entry.assets,
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

  async function pin(entry: Entry) {
    if (
      busy ||
      disabled ||
      loadedVersion !== refreshVersion ||
      draft.original?.id === entry.id ||
      pinBlocked.includes(entry.id)
    )
      return;
    firstRequest.current?.abort();
    nextRequest.current?.abort();
    setLoading(false);
    setCursor(null);
    writing(true);
    setActionError('');
    setSaved('');
    try {
      const updated = await setEntryPinned(
        entry,
        !entry.is_pinned,
        session.csrf_token,
      );
      setSaved(updated.is_pinned ? '日记已置顶。' : '已取消置顶。');
      refreshList();
    } catch (cause) {
      if (isUnauthorized(cause)) onExpired();
      else {
        setPinBlocked((current) => [...current, entry.id]);
        setActionError(
          cause instanceof ApiError && cause.status === 409
            ? '这篇日记已有修改，请刷新列表、核对置顶状态后再操作。'
            : cause instanceof ApiError && cause.status === 0
              ? '置顶结果尚未确认。请刷新列表核对，再决定是否重试。'
              : `${errorMessage(cause)} 请刷新列表核对置顶状态。`,
        );
      }
    } finally {
      writing(false);
    }
  }

  async function remove(entry: Entry) {
    if (busy || disabled) return;
    if (
      !window.confirm(
        `确认删除 ${entry.entry_date} 的这篇日记吗？删除后可从回收站恢复。`,
      )
    )
      return;
    writing(true);
    setActionError('');
    try {
      await deleteEntry(entry, session.csrf_token);
      setEntries((current) => current.filter((item) => item.id !== entry.id));
      setSaved('日记已删除，可从回收站恢复。');
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
        tags={tags}
        tagsLoading={tagsLoading}
        tagsError={tagsError}
        onTagCreated={(tag) =>
          setTags((current) =>
            [...current.filter((item) => item.id !== tag.id), tag].sort(
              (a, b) => a.name.localeCompare(b.name, 'zh-CN'),
            ),
          )
        }
        onTagsRetry={() => {
          setTagsLoading(true);
          setTagsError('');
          setTagsRefresh((value) => value + 1);
        }}
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
        <div className="tag-filter">
          <label htmlFor="journal-tag-filter">按标签筛选</label>
          <select
            id="journal-tag-filter"
            value={filterTagId}
            disabled={busy || disabled || tagsLoading}
            onChange={(event) => {
              firstRequest.current?.abort();
              nextRequest.current?.abort();
              setEntries([]);
              setCursor(null);
              setLoading(true);
              setListError('');
              setFilterTagId(event.target.value);
            }}
          >
            <option value="">全部标签</option>
            {tags.map((tag) => (
              <option key={tag.id} value={tag.id}>
                {tag.name}
              </option>
            ))}
          </select>
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
            onPin={(item) => void pin(item)}
            pinDisabled={
              loadedVersion !== refreshVersion || pinBlocked.includes(entry.id)
            }
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
            <h3>{filterTagId ? '这个标签下还没有记录' : '还没有记录'}</h3>
            <p>
              {filterTagId
                ? '保存带有此标签的日记后，会显示在这里。'
                : '从一件小事开始，写下你的第一篇日记。'}
            </p>
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
