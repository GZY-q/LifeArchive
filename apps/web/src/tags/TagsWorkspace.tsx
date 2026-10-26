import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';

import { ApiError, errorMessage, isUnauthorized } from '../api/client';
import { listTags, renameTag } from '../api/tags';
import type { Tag } from '../api/tags';

type Props = {
  csrfToken: string;
  disabled: boolean;
  onExpired: () => void;
  onBusy: (busy: boolean) => void;
  onCatalogue: () => void;
};

type Edit = { tag: Tag; name: string };

export function TagsWorkspace({
  csrfToken,
  disabled,
  onExpired,
  onBusy,
  onCatalogue,
}: Props) {
  const [tags, setTags] = useState<Tag[]>([]);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [edit, setEdit] = useState<Edit | null>(null);
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [requiresRead, setRequiresRead] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const writing = useRef(false);
  const composing = useRef(false);
  const mounted = useRef(false);
  const locked = disabled || busy || loading;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void listTags(controller.signal)
      .then((items) => {
        if (controller.signal.aborted) return;
        setTags(items);
        setRequiresRead(false);
        onCatalogue();
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(cause)) onExpired();
        else setLoadError(errorMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refresh, onExpired, onCatalogue]);

  function reload() {
    if (locked || writing.current) return;
    setLoading(true);
    setLoadError('');
    // Reading never silently rebases a failed write onto the latest name.
    if (edit) {
      setBlocked(true);
      setNotice('读取完成后，请在目录中选择标签重新编辑；已输入的名称仍保留。');
    }
    setRefresh((value) => value + 1);
  }

  function begin(tag: Tag) {
    if (locked || loadError || requiresRead || writing.current) return;
    setEdit({ tag, name: edit?.tag.id === tag.id ? edit.name : tag.name });
    setBlocked(false);
    setError('');
    setNotice('');
    composing.current = false;
  }

  async function save() {
    if (
      locked ||
      blocked ||
      writing.current ||
      composing.current ||
      !edit?.name.trim()
    )
      return;
    writing.current = true;
    setBusy(true);
    onBusy(true);
    setError('');
    setNotice('');
    try {
      const tag = await renameTag(
        edit.tag.id,
        edit.name,
        edit.tag.name,
        csrfToken,
      );
      if (!mounted.current) return;
      setTags((items) =>
        items
          .map((item) => (item.id === tag.id ? tag : item))
          .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN')),
      );
      setEdit(null);
      setNotice('标签名称已更新，日记关联与历史名称快照仍保留。');
      onCatalogue();
    } catch (cause) {
      if (!mounted.current) return;
      if (isUnauthorized(cause)) onExpired();
      else if (
        cause instanceof ApiError &&
        (cause.status === 409 || cause.status === 0 || cause.status >= 500)
      ) {
        setBlocked(true);
        setRequiresRead(true);
        setError(
          cause.status === 409
            ? cause.code === 'tag_name_taken'
              ? '名称已被其他标签使用。请重新读取目录，再选择标签重新编辑。'
              : '标签已在其他页面更改。请重新读取目录，再选择标签重新编辑。'
            : '改名结果尚未确认，未自动重试。请重新读取目录，再选择标签重新编辑。',
        );
      } else if (cause instanceof ApiError && cause.status === 404) {
        setBlocked(true);
        setRequiresRead(true);
        setError('标签已不可用。请重新读取目录。');
      } else if (cause instanceof ApiError && cause.status === 422) {
        setError('标签名称须为 1–40 个字符，不能包含控制字符或换行。');
      } else setError(errorMessage(cause));
    } finally {
      writing.current = false;
      if (mounted.current) {
        setBusy(false);
        onBusy(false);
      }
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void save();
  }

  return (
    <section
      className="paper-card tags-workspace"
      aria-labelledby="tags-title"
      aria-busy={loading || busy}
    >
      <h2 id="tags-title">标签管理</h2>
      <p className="small-note">
        改名会更新当前日记中的标签名称，修订历史保留当时的名称。创建标签仍可在日记编辑区完成。
      </p>
      <button
        type="button"
        className="secondary-button"
        disabled={locked}
        onClick={reload}
      >
        重新读取标签目录
      </button>
      {loading && <p role="status">正在读取标签目录…</p>}
      {loadError && (
        <p className="error-message" role="alert">
          标签目录读取失败。{loadError}
        </p>
      )}
      {!loading && !loadError && !tags.length && (
        <p className="empty-state">还没有标签，请在日记编辑区创建。</p>
      )}
      {tags.length > 0 && (
        <ul className="tag-catalogue" aria-label="标签目录">
          {tags.map((tag) => (
            <li key={tag.id}>
              <span>{tag.name}</span>
              <button
                type="button"
                className="text-button"
                disabled={locked || !!loadError || requiresRead}
                onClick={() => begin(tag)}
                aria-label={`改名 ${tag.name}`}
              >
                {blocked && edit?.tag.id === tag.id ? '重新编辑' : '改名'}
              </button>
            </li>
          ))}
        </ul>
      )}
      {edit && (
        <form className="tag-rename-form" onSubmit={submit} noValidate>
          <p className="small-note">编辑时的名称：{edit.tag.name}</p>
          <label htmlFor="rename-tag-name">新标签名称</label>
          <input
            id="rename-tag-name"
            value={edit.name}
            maxLength={256}
            disabled={locked || blocked}
            autoComplete="off"
            onChange={(event) => setEdit({ ...edit, name: event.target.value })}
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
          />
          <div className="entry-actions">
            <button
              type="submit"
              className="primary-button"
              disabled={locked || blocked || !edit.name.trim()}
            >
              {busy ? '正在改名…' : '保存标签名称'}
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={locked}
              onClick={() => {
                setEdit(null);
                setBlocked(false);
                setError('');
              }}
            >
              取消编辑
            </button>
          </div>
        </form>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="success-message" role="status">
          {notice}
        </p>
      )}
    </section>
  );
}
