import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';

import { errorMessage, isUnauthorized } from '../api/client';
import type { Entry } from '../api/journal';
import { searchEntries } from '../api/search';
import type { SearchFilters } from '../api/search';
import { listTags } from '../api/tags';
import type { Tag } from '../api/tags';
import { TagBadges } from '../journal/TagBadges';
import { AssetGallery } from '../journal/AssetGallery';
import { PinnedBadge } from '../journal/PinnedBadge';
import { readSearchForm } from './form';
import type { SearchForm } from './form';

type Props = {
  form: SearchForm;
  onForm: (form: SearchForm) => void;
  csrfToken: string;
  onExpired: () => void;
  disabled: boolean;
};

export function ArchiveWorkspace({
  form,
  onForm,
  csrfToken,
  onExpired,
  disabled,
}: Props) {
  const [submitted, setSubmitted] = useState<SearchFilters | null>(null);
  const [submittedTagName, setSubmittedTagName] = useState<string | null>(null);
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagsLoading, setTagsLoading] = useState(true);
  const [tagsError, setTagsError] = useState('');
  const [tagsRefresh, setTagsRefresh] = useState(0);
  const [items, setItems] = useState<Entry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [requestError, setRequestError] = useState('');
  const [failedCursor, setFailedCursor] = useState<string | null>(null);
  const composing = useRef(false);
  const requestVersion = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void listTags(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setTags(items);
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

  useEffect(
    () => () => {
      requestVersion.current += 1;
      activeRequest.current?.abort();
    },
    [],
  );

  async function load(filters: SearchFilters, page: string | null = null) {
    if (disabled) return;
    const version = ++requestVersion.current;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setBusy(true);
    setRequestError('');
    setFailedCursor(null);
    if (page === null) {
      setSubmitted(filters);
      setItems([]);
      setCursor(null);
    }
    try {
      const result = await searchEntries(
        filters,
        csrfToken,
        page,
        controller.signal,
      );
      if (controller.signal.aborted || version !== requestVersion.current)
        return;
      setItems((previous) => {
        if (page === null) return result.items;
        const known = new Set(previous.map((entry) => entry.id));
        return [
          ...previous,
          ...result.items.filter((entry) => !known.has(entry.id)),
        ];
      });
      setCursor(result.next_cursor);
    } catch (cause) {
      if (controller.signal.aborted || version !== requestVersion.current)
        return;
      if (isUnauthorized(cause)) onExpired();
      else {
        setRequestError(errorMessage(cause));
        setFailedCursor(page);
      }
    } finally {
      if (!controller.signal.aborted && version === requestVersion.current)
        setBusy(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled || composing.current) return;
    const result = readSearchForm(form);
    setFormError(result.error ?? '');
    if (result.filters) {
      setSubmittedTagName(
        result.filters.tag_id
          ? (tags.find((tag) => tag.id === result.filters.tag_id)?.name ??
              '已选标签')
          : null,
      );
      void load(result.filters);
    }
  }

  return (
    <section className="archive-workspace" aria-label="归档搜索">
      <div className="paper-card archive-panel">
        <h2>查找过去的记录</h2>
        <p className="small-note" id="archive-help">
          按原文中的连续文字查找，支持中文与英文，英文不区分大小写。
          也可以只按日记日期或标签筛选；组合条件同时满足，开始和结束日期均包含在内。
        </p>
        <form className="archive-form" onSubmit={submit} noValidate>
          <label htmlFor="archive-query">关键词</label>
          <input
            id="archive-query"
            type="text"
            value={form.query}
            onChange={(event) => onForm({ ...form, query: event.target.value })}
            onCompositionStart={() => {
              composing.current = true;
            }}
            onCompositionEnd={() => {
              composing.current = false;
            }}
            onKeyDown={(event) => {
              if (
                event.key === 'Enter' &&
                (event.nativeEvent.isComposing || composing.current)
              )
                event.preventDefault();
            }}
            disabled={disabled}
            autoComplete="off"
            spellCheck={false}
            aria-describedby="archive-help"
          />
          <div className="archive-dates">
            <label htmlFor="archive-date-from">
              开始日期
              <input
                id="archive-date-from"
                type="date"
                min="0001-01-01"
                max="9999-12-31"
                value={form.date_from}
                onChange={(event) =>
                  onForm({ ...form, date_from: event.target.value })
                }
                disabled={disabled}
              />
            </label>
            <label htmlFor="archive-date-to">
              结束日期
              <input
                id="archive-date-to"
                type="date"
                min="0001-01-01"
                max="9999-12-31"
                value={form.date_to}
                onChange={(event) =>
                  onForm({ ...form, date_to: event.target.value })
                }
                disabled={disabled}
              />
            </label>
          </div>
          <label htmlFor="archive-tag">标签</label>
          <select
            id="archive-tag"
            value={form.tag_id}
            disabled={disabled || tagsLoading}
            onChange={(event) =>
              onForm({ ...form, tag_id: event.target.value })
            }
          >
            <option value="">不限标签</option>
            {form.tag_id && !tags.some((tag) => tag.id === form.tag_id) && (
              <option value={form.tag_id}>已选标签</option>
            )}
            {tags.map((tag) => (
              <option key={tag.id} value={tag.id}>
                {tag.name}
              </option>
            ))}
          </select>
          {tagsLoading && (
            <p className="small-note" role="status">
              正在读取标签…
            </p>
          )}
          {tagsError && (
            <div>
              <p className="error-message" role="alert">
                标签目录读取失败。{tagsError}
              </p>
              <button
                type="button"
                className="text-button"
                disabled={disabled || tagsLoading}
                onClick={() => {
                  setTagsLoading(true);
                  setTagsError('');
                  setTagsRefresh((value) => value + 1);
                }}
              >
                重试读取标签
              </button>
            </div>
          )}
          {formError && (
            <p className="error-message" role="alert">
              {formError}
            </p>
          )}
          <button className="primary-button" type="submit" disabled={disabled}>
            搜索日记
          </button>
        </form>
      </div>
      {submitted ? (
        <section
          className="archive-results"
          aria-label="搜索结果"
          aria-busy={busy}
        >
          <h2>搜索结果</h2>
          <p className="small-note archive-summary">
            已提交条件：
            {submitted.query ? `关键词「${submitted.query}」` : '不限关键词'}
            {' · '}
            {submitted.date_from ?? '最早'} 至 {submitted.date_to ?? '最新'}
            {' · '}
            {submittedTagName ? `标签「${submittedTagName}」` : '不限标签'}
          </p>
          {busy && (
            <p className="small-note" role="status">
              正在搜索日记…
            </p>
          )}
          {requestError && (
            <div>
              <p className="error-message" role="alert">
                {requestError}
              </p>
              <button
                type="button"
                className="secondary-button"
                onClick={() => void load(submitted, failedCursor)}
                disabled={disabled || busy}
              >
                重试搜索
              </button>
            </div>
          )}
          {!busy && !requestError && items.length === 0 && (
            <p className="empty-state">没有找到符合条件的日记。</p>
          )}
          {items.map((entry) => (
            <article className="paper-card archive-entry" key={entry.id}>
              <p className="small-note">
                <time dateTime={entry.entry_date}>{entry.entry_date}</time>
                {' · '}版本 {entry.revision}
              </p>
              <PinnedBadge isPinned={entry.is_pinned} />
              <pre className="markdown-text">{entry.content_md}</pre>
              <TagBadges tags={entry.tags} />
              <AssetGallery assets={entry.assets} onExpired={onExpired} />
            </article>
          ))}
          {cursor && !requestError && (
            <button
              type="button"
              className="secondary-button load-more"
              disabled={disabled || busy}
              onClick={() => void load(submitted, cursor)}
            >
              加载更多结果
            </button>
          )}
        </section>
      ) : (
        <p className="empty-state">
          输入关键词，或选择日记日期、标签，再点击搜索日记。
        </p>
      )}
    </section>
  );
}
