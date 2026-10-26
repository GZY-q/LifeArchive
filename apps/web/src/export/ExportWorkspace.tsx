import { useEffect, useRef, useState } from 'react';

import { isUnauthorized } from '../api/client';
import { exportError, exportJournal } from '../api/export';

type Props = {
  csrfToken: string;
  disabled: boolean;
  onExpired: () => void;
};

type Download = { url: string; includeDeleted: boolean; bytes: number };

export function ExportWorkspace({ csrfToken, disabled, onExpired }: Props) {
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [download, setDownload] = useState<Download | null>(null);
  const pending = useRef<AbortController | null>(null);
  const objectUrl = useRef('');

  function discardDownload() {
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = '';
    setDownload(null);
  }

  useEffect(() => {
    return () => {
      pending.current?.abort();
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    };
  }, []);

  async function generate() {
    if (disabled || pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    discardDownload();
    setBusy(true);
    setError('');
    try {
      const blob = await exportJournal(
        includeDeleted,
        csrfToken,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      objectUrl.current = URL.createObjectURL(blob);
      setDownload({ url: objectUrl.current, includeDeleted, bytes: blob.size });
    } catch (cause) {
      if (controller.signal.aborted) return;
      if (isUnauthorized(cause)) onExpired();
      else setError(exportError(cause));
    } finally {
      if (!controller.signal.aborted) {
        pending.current = null;
        setBusy(false);
      }
    }
  }

  return (
    <section
      className="paper-card export-workspace"
      aria-labelledby="export-title"
      aria-busy={busy}
    >
      <h2 id="export-title">导出日记</h2>
      <p>
        下载原始 Markdown、JSON
        元数据、全部所选修订和当前及历史引用的原图。导出不会修改日记，未保存的草稿不包含在内。
      </p>
      <p className="small-note">
        ZIP
        未加密，包含私密内容，请妥善保管。未关联日记的上传、登录凭据和配置不在其中；应用导出不能替代数据库和原文件备份。
      </p>
      <label className="export-option">
        <input
          type="checkbox"
          checked={includeDeleted}
          disabled={disabled || busy}
          onChange={(event) => {
            setIncludeDeleted(event.target.checked);
            discardDownload();
            setError('');
          }}
        />
        包含回收站中的日记及其全部修订和原图
      </label>
      <p className="small-note">
        网页上限为 1,000 篇日记、5,000 条修订、2,000 个标签和 32 MiB
        ZIP。超出时可使用命令行导出完整档案。
      </p>
      <button
        type="button"
        className="primary-button"
        disabled={disabled || busy}
        onClick={() => void generate()}
      >
        {busy ? '正在生成…' : '生成导出文件'}
      </button>
      {busy && (
        <p role="status">
          正在读取并校验档案。离开此页将取消下载，当前日记草稿仍保留。
        </p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {download && (
        <div className="export-download">
          <p role="status">
            导出文件已准备好：
            {download.includeDeleted ? '包含回收站' : '仅活动日记'}，
            {(download.bytes / 1024 / 1024).toLocaleString('zh-CN', {
              maximumFractionDigits: 2,
            })}{' '}
            MiB。
          </p>
          <a href={download.url} download="life-archive-journal.zip">
            下载日记 ZIP
          </a>
          <p className="small-note">
            这是生成时的档案快照；之后的修改需重新生成。离开此页后下载链接失效。
          </p>
        </div>
      )}
    </section>
  );
}
