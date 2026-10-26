import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';

import type { Asset } from '../api/assets';
import {
  IMAGE_TYPES,
  imageError,
  MAX_IMAGE_BYTES,
  uploadAsset,
} from '../api/assets';
import { isUnauthorized } from '../api/client';
import { AssetGallery } from './AssetGallery';

type Props = {
  assets: Asset[];
  csrfToken: string;
  disabled: boolean;
  onChange: (assets: Asset[]) => void;
  onBusy: (busy: boolean) => void;
  onExpired: () => void;
};

export function AssetPicker({
  assets,
  csrfToken,
  disabled,
  onChange,
  onBusy,
  onExpired,
}: Props) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const active = useRef<AbortController | null>(null);
  const writing = useRef(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      active.current?.abort();
    };
  }, []);

  async function select(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || disabled || writing.current || assets.length >= 10) return;
    setError('');
    if (
      !IMAGE_TYPES.includes(file.type) ||
      file.size === 0 ||
      file.size > MAX_IMAGE_BYTES
    ) {
      setError('请选择不超过 5 MiB 的 JPEG、PNG 或 WebP 原图。');
      return;
    }
    const controller = new AbortController();
    active.current = controller;
    writing.current = true;
    setUploading(true);
    onBusy(true);
    try {
      const asset = await uploadAsset(file, csrfToken, controller.signal);
      if (!mounted.current) return;
      if (!assets.some((item) => item.id === asset.id))
        onChange([...assets, asset].sort((a, b) => a.id.localeCompare(b.id)));
    } catch (cause) {
      if (!mounted.current) return;
      if (isUnauthorized(cause)) onExpired();
      else setError(`${imageError(cause)} 可重新选择同一文件重试。`);
    } finally {
      writing.current = false;
      if (mounted.current) setUploading(false);
      onBusy(false);
    }
  }

  return (
    <fieldset className="asset-picker" disabled={disabled || uploading}>
      <legend>
        图片 <span className="small-note">{assets.length} / 10</span>
      </legend>
      <label htmlFor="journal-image">选择图片</label>
      <input
        id="journal-image"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        disabled={disabled || uploading || assets.length >= 10}
        onChange={(event) => void select(event)}
      />
      {uploading && (
        <p className="small-note" role="status">
          正在上传原图…
        </p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {assets.map((asset, index) => (
        <div key={asset.id} className="asset-selection">
          <span className="small-note">
            图片 {index + 1} · {asset.width} × {asset.height}
          </span>
          <button
            type="button"
            className="text-button"
            disabled={disabled || uploading}
            onClick={() =>
              onChange(assets.filter((item) => item.id !== asset.id))
            }
          >
            移除图片 {index + 1}
          </button>
        </div>
      ))}
      <AssetGallery assets={assets} onExpired={onExpired} />
      <p className="small-note">
        每张最多 5 MiB，支持静态 JPEG、PNG 和
        WebP。所选图片随日记保存；移除仅取消关联，原文件仍保留。
      </p>
    </fieldset>
  );
}
