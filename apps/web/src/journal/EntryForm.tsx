import { useState } from 'react';
import type { FormEvent } from 'react';

import { ApiError, errorMessage, isUnauthorized } from '../api/client';
import { createEntry, getEntry, updateEntry } from '../api/journal';
import type { Entry } from '../api/journal';
import type { Tag } from '../api/tags';
import { MarkdownEditor } from '../components/MarkdownEditor';
import type { Draft } from './draft';
import { TagBadges } from './TagBadges';
import { TagPicker } from './TagPicker';
import { AssetGallery } from './AssetGallery';
import { PinnedBadge } from './PinnedBadge';
import { AssetPicker } from './AssetPicker';

type Props = {
  draft: Draft;
  csrfToken: string;
  disabled: boolean;
  onDraft: (draft: Draft) => void;
  onSaved: () => void;
  onCancel: () => void;
  onExpired: () => void;
  onBusy: (busy: boolean) => void;
  tags: Tag[];
  tagsLoading: boolean;
  tagsError: string;
  onTagCreated: (tag: Tag) => void;
  onTagsRetry: () => void;
};

export function EntryForm({
  draft,
  csrfToken,
  disabled,
  onDraft,
  onSaved,
  onCancel,
  onExpired,
  onBusy,
  tags,
  tagsLoading,
  tagsError,
  onTagCreated,
  onTagsRetry,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [composing, setComposing] = useState(false);
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(false);
  const [latest, setLatest] = useState<Entry | null>(null);
  const [loadingLatest, setLoadingLatest] = useState(false);
  const editing = draft.original !== null;
  const locked = disabled || busy || uploading || draft.pendingCreate !== null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      busy ||
      disabled ||
      uploading ||
      composing ||
      conflict ||
      !draft.content_md.trim()
    )
      return;
    setBusy(true);
    onBusy(true);
    setError('');
    try {
      if (draft.original) {
        await updateEntry(
          draft.original.id,
          {
            content_md: draft.content_md,
            entry_date: draft.entry_date,
            tag_ids: draft.tag_ids,
            asset_ids: draft.asset_ids,
            expected_revision: draft.original.revision,
          },
          csrfToken,
        );
      } else {
        const input = draft.pendingCreate ?? {
          content_md: draft.content_md,
          entry_date: draft.entry_date,
          tag_ids: [...draft.tag_ids],
          asset_ids: [...draft.asset_ids],
          client_request_id: crypto.randomUUID(),
        };
        onDraft({ ...draft, pendingCreate: input });
        await createEntry(input, csrfToken);
      }
      onSaved();
    } catch (cause) {
      if (isUnauthorized(cause)) {
        onExpired();
      } else if (cause instanceof ApiError && cause.status === 409 && editing) {
        setConflict(true);
        setError(
          '这篇日记已有新的版本。你的草稿仍保留，请先读取最新版本再决定如何保存。',
        );
      } else {
        // Only a rejection of the initial attempt proves that nothing was saved.
        // A rejected retry says nothing about the earlier uncertain attempt, so
        // keep that exact body and UUID until its result can be confirmed.
        if (
          !editing &&
          !draft.pendingCreate &&
          cause instanceof ApiError &&
          cause.status >= 400 &&
          cause.status < 500 &&
          cause.status !== 409
        )
          onDraft({ ...draft, pendingCreate: null });
        setError(errorMessage(cause));
      }
    } finally {
      setBusy(false);
      onBusy(false);
    }
  }

  async function readLatest() {
    if (!draft.original) return;
    setLoadingLatest(true);
    try {
      setLatest(await getEntry(draft.original.id));
    } catch (cause) {
      if (isUnauthorized(cause)) onExpired();
      else setError(errorMessage(cause));
    } finally {
      setLoadingLatest(false);
    }
  }

  return (
    <section className="composer paper-card" aria-labelledby="composer-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">KEEP A MOMENT</p>
          <h2 id="composer-title">{editing ? '编辑这篇日记' : '写下今天'}</h2>
        </div>
        {editing && (
          <button
            type="button"
            className="text-button"
            disabled={busy || disabled}
            onClick={onCancel}
          >
            取消编辑
          </button>
        )}
      </div>
      <form onSubmit={(event) => void submit(event)}>
        <div className="date-field">
          <label htmlFor="entry-date">日记日期</label>
          <input
            id="entry-date"
            type="date"
            required
            value={draft.entry_date}
            disabled={locked}
            onChange={(event) =>
              onDraft({ ...draft, entry_date: event.target.value })
            }
          />
        </div>
        <label htmlFor="journal-content" className="editor-label">
          日记内容
        </label>
        <MarkdownEditor
          id="journal-content"
          value={draft.content_md}
          disabled={locked}
          onChange={(content_md) => onDraft({ ...draft, content_md })}
          onComposing={setComposing}
        />
        <p id="journal-content-hint" className="small-note">
          Markdown 原文 · 仅保存在当前页面，保存后才写入档案。
        </p>
        <TagPicker
          tags={tags}
          selected={draft.tag_ids}
          original={draft.original?.tags ?? []}
          csrfToken={csrfToken}
          disabled={locked}
          loading={tagsLoading}
          error={tagsError}
          onChange={(tag_ids) => onDraft({ ...draft, tag_ids })}
          onCreated={onTagCreated}
          onRetry={onTagsRetry}
          onExpired={onExpired}
          onBusy={onBusy}
        />
        <AssetPicker
          assets={draft.attachments}
          csrfToken={csrfToken}
          disabled={locked}
          onChange={(attachments) =>
            onDraft({
              ...draft,
              attachments,
              asset_ids: attachments.map((asset) => asset.id),
            })
          }
          onExpired={onExpired}
          onBusy={(value) => {
            setUploading(value);
            onBusy(value);
          }}
        />
        {error && (
          <p className="error-message" role="alert">
            {error}
          </p>
        )}
        {!busy && draft.pendingCreate && (
          <p className="notice">
            保存结果尚未确认。请先重试相同内容，确认后才能继续修改，以免产生重复记录。
          </p>
        )}
        {conflict && (
          <div className="conflict-panel">
            <button
              type="button"
              className="secondary-button"
              disabled={loadingLatest || disabled}
              onClick={() => void readLatest()}
            >
              {loadingLatest ? '正在读取…' : '读取最新版本'}
            </button>
            {latest && (
              <>
                <h3>
                  服务器版本 {latest.revision} · {latest.entry_date}
                </h3>
                <PinnedBadge isPinned={latest.is_pinned} />
                <pre className="markdown-text">{latest.content_md}</pre>
                <TagBadges tags={latest.tags} />
                <AssetGallery assets={latest.assets} onExpired={onExpired} />
                <button
                  type="button"
                  className="secondary-button"
                  disabled={disabled}
                  onClick={() => {
                    onDraft({ ...draft, original: latest });
                    setConflict(false);
                    setLatest(null);
                    setError('');
                  }}
                >
                  保留草稿，基于新版继续
                </button>
                <p className="small-note">
                  此操作保留你的内容；再次保存前，请先核对两个版本。
                </p>
              </>
            )}
          </div>
        )}
        <div className="composer-actions">
          <span className="small-note">
            {draft.content_md.length.toLocaleString()} / 100,000
          </span>
          <button
            className="primary-button"
            type="submit"
            disabled={
              busy ||
              uploading ||
              disabled ||
              composing ||
              conflict ||
              !draft.content_md.trim()
            }
          >
            {busy
              ? '正在保存…'
              : draft.pendingCreate
                ? '重试保存'
                : editing
                  ? '保存修改'
                  : '保存日记'}
          </button>
        </div>
      </form>
    </section>
  );
}
