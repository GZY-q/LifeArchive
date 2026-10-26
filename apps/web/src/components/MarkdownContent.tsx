import { useState } from 'react';

import { MarkdownPreview } from './MarkdownPreview';

/** Raw text stays the default; changing the display never changes the source. */
export function MarkdownContent({
  content,
  label = 'Markdown 内容',
  disabled = false,
}: {
  content: string;
  label?: string;
  disabled?: boolean;
}) {
  const [preview, setPreview] = useState(false);
  return (
    <div className="markdown-content" aria-label={label}>
      <button
        type="button"
        className="text-button markdown-display-toggle"
        aria-pressed={preview}
        disabled={disabled}
        onClick={() => setPreview((value) => !value)}
      >
        {preview ? '查看原文' : '预览 Markdown'}
      </button>
      {preview ? (
        <MarkdownPreview content={content} label={`${label}预览`} />
      ) : (
        <pre className="markdown-text">{content}</pre>
      )}
    </div>
  );
}
