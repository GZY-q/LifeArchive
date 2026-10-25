import { useState } from 'react';

import { errorMessage, isUnauthorized } from '../api/client';
import { createTag } from '../api/tags';
import type { Tag, TagLabel } from '../api/tags';

type Props = {
  tags: Tag[];
  selected: string[];
  original: TagLabel[];
  csrfToken: string;
  disabled: boolean;
  loading: boolean;
  error: string;
  onChange: (ids: string[]) => void;
  onCreated: (tag: Tag) => void;
  onRetry: () => void;
  onExpired: () => void;
  onBusy: (busy: boolean) => void;
};

export function TagPicker({
  tags,
  selected,
  original,
  csrfToken,
  disabled,
  loading,
  error,
  onChange,
  onCreated,
  onRetry,
  onExpired,
  onBusy,
}: Props) {
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const options: TagLabel[] = [
    ...tags,
    ...original.filter((tag) => !tags.some((item) => item.id === tag.id)),
  ];
  const locked = disabled || creating;

  async function add() {
    if (locked || !name.trim() || selected.length >= 20) return;
    setCreating(true);
    onBusy(true);
    setCreateError('');
    try {
      const tag = await createTag(name, csrfToken);
      onCreated(tag);
      if (!selected.includes(tag.id)) onChange([...selected, tag.id].sort());
      setName('');
    } catch (cause) {
      if (isUnauthorized(cause)) onExpired();
      else setCreateError(errorMessage(cause));
    } finally {
      setCreating(false);
      onBusy(false);
    }
  }

  return (
    <fieldset className="tag-picker" disabled={locked}>
      <legend>
        标签 <span className="small-note">{selected.length} / 20</span>
      </legend>
      {loading && (
        <p className="small-note" role="status">
          正在读取标签…
        </p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {error && (
        <button type="button" className="text-button" onClick={onRetry}>
          重试读取标签
        </button>
      )}
      <div className="tag-options">
        {options.map((tag) => (
          <label key={tag.id}>
            <input
              type="checkbox"
              checked={selected.includes(tag.id)}
              disabled={
                locked || (!selected.includes(tag.id) && selected.length >= 20)
              }
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...selected, tag.id].sort()
                    : selected.filter((id) => id !== tag.id),
                )
              }
            />
            <span>{tag.name}</span>
          </label>
        ))}
      </div>
      {!loading && !error && !options.length && (
        <p className="small-note">还没有标签，创建一个来整理日记。</p>
      )}
      <div className="tag-create">
        <label htmlFor="new-tag-name" className="visually-hidden">
          新标签名称
        </label>
        <input
          id="new-tag-name"
          value={name}
          maxLength={256}
          placeholder="新标签，最多 40 字"
          onChange={(event) => setName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') event.preventDefault();
          }}
        />
        <button
          type="button"
          className="secondary-button"
          disabled={locked || !name.trim() || selected.length >= 20}
          onClick={() => void add()}
        >
          {creating ? '正在创建…' : '创建并选择标签'}
        </button>
      </div>
      {createError && (
        <p className="error-message" role="alert">
          {createError}
        </p>
      )}
      <p className="small-note">
        所选标签随日记一起保存。创建的标签会保留在目录中。
      </p>
    </fieldset>
  );
}
