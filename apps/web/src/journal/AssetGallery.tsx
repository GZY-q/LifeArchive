import { useEffect, useState } from 'react';

import type { Asset } from '../api/assets';
import { imageError, imageExtension, readAsset } from '../api/assets';
import { isUnauthorized } from '../api/client';

function AssetPreview({
  asset,
  onExpired,
}: {
  asset: Asset;
  onExpired: () => void;
}) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = '';
    void readAsset(asset, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(cause)) onExpired();
        else setError(imageError(cause));
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [asset, retry, onExpired]);

  return (
    <figure className="asset-preview">
      {url && (
        <img
          src={url}
          alt="日记图片附件"
          width={asset.width}
          height={asset.height}
          loading="lazy"
        />
      )}
      {!url && !error && (
        <p className="small-note" role="status">
          正在读取原图…
        </p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {error && (
        <button
          type="button"
          className="text-button"
          onClick={() => {
            setError('');
            setRetry((value) => value + 1);
          }}
        >
          重试读取图片
        </button>
      )}
      <figcaption className="small-note">
        {asset.width} × {asset.height} ·{' '}
        {(asset.byte_size / 1024).toLocaleString('zh-CN', {
          maximumFractionDigits: 1,
        })}{' '}
        KiB
        {url && (
          <>
            {' '}
            ·{' '}
            <a
              href={url}
              download={`image-${asset.id}.${imageExtension(asset.mime_type)}`}
            >
              下载原图
            </a>
          </>
        )}
      </figcaption>
    </figure>
  );
}

/** Expanding mounts authenticated reads; collapsing revokes every object URL. */
export function AssetGallery({
  assets,
  onExpired,
}: {
  assets: Asset[];
  onExpired: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!assets.length) return null;
  return (
    <section className="asset-gallery" aria-label="图片附件">
      <button
        type="button"
        className="text-button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? '收起图片' : `查看图片（${assets.length}）`}
      </button>
      {expanded && (
        <div className="asset-grid">
          {assets.map((asset) => (
            <AssetPreview key={asset.id} asset={asset} onExpired={onExpired} />
          ))}
        </div>
      )}
    </section>
  );
}
