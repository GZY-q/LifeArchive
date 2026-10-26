import { useDeferredValue } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import './markdown.css';

const allowedElements = [
  'a',
  'blockquote',
  'br',
  'code',
  'del',
  'em',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'hr',
  'li',
  'ol',
  'p',
  'pre',
  'strong',
  'ul',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
  'input',
  'img',
];

function safeHref(value: string): string | undefined {
  if (!/^https?:\/\//i.test(value)) return;
  for (const character of value) {
    const code = character.charCodeAt(0);
    if (code <= 0x20 || (code >= 0x7f && code <= 0x9f)) return;
  }
  try {
    const url = new URL(value);
    if (
      !['http:', 'https:'].includes(url.protocol) ||
      !url.hostname ||
      url.username ||
      url.password
    )
      return;
    return url.href;
  } catch {
    return;
  }
}

/** Rendering is local and read-only; private images remain in AssetGallery. */
export function MarkdownPreview({
  content,
  label = 'Markdown 预览',
}: {
  content: string;
  label?: string;
}) {
  const deferredContent = useDeferredValue(content);
  return (
    <div className="markdown-preview" aria-label={label}>
      <ReactMarkdown
        skipHtml
        allowedElements={allowedElements}
        remarkPlugins={[remarkGfm]}
        urlTransform={(url, key) =>
          key === 'href' ? (safeHref(url) ?? '') : ''
        }
        components={{
          a: ({ href, children }) => {
            const safe = href ? safeHref(href) : undefined;
            return safe ? (
              <a
                href={safe}
                target="_blank"
                rel="noopener noreferrer"
                referrerPolicy="no-referrer"
              >
                {children}
              </a>
            ) : (
              <span>{children}</span>
            );
          },
          img: ({ alt }) => (
            <span className="markdown-image-placeholder">
              图片{alt ? `：${alt}` : ''}（请使用私密图库）
            </span>
          ),
          input: ({ checked }) => (
            <input
              type="checkbox"
              checked={checked === true}
              disabled
              readOnly
              aria-label={checked ? '已完成任务' : '未完成任务'}
            />
          ),
        }}
      >
        {deferredContent}
      </ReactMarkdown>
    </div>
  );
}
