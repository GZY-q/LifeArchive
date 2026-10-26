import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MarkdownContent } from './MarkdownContent';
import { MarkdownPreview } from './MarkdownPreview';

describe('safe Markdown preview', () => {
  it('renders CommonMark and GFM as read-only local content', () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const { container } = render(
      <MarkdownPreview
        content={[
          '# 今天',
          '',
          '**重点** 与 *回忆*，~~过去~~。',
          '',
          '> 一段引用',
          '',
          '- 普通列表',
          '- [x] 已完成',
          '- [ ] 待办',
          '',
          '用 `code` 记下。',
          '',
          '```js',
          'const value = "原文";',
          '```',
          '',
          '| 日期 | 记忆 |',
          '| --- | --- |',
          '| 今天 | 小事 |',
          '',
          '---',
        ].join('\n')}
      />,
    );
    expect(screen.getByRole('heading', { name: '今天' })).toBeInTheDocument();
    expect(container.querySelector('strong')).toHaveTextContent('重点');
    expect(container.querySelector('em')).toHaveTextContent('回忆');
    expect(container.querySelector('del')).toHaveTextContent('过去');
    expect(container.querySelector('blockquote')).toHaveTextContent('一段引用');
    expect(screen.getByRole('table')).toHaveTextContent('小事');
    expect(container.querySelector('pre code')).toHaveTextContent(
      'const value = "原文";',
    );
    const complete = screen.getByRole('checkbox', { name: '已完成任务' });
    expect(complete).toBeChecked();
    expect(complete).toBeDisabled();
    expect(complete).toHaveAttribute('readonly');
    expect(screen.getByRole('checkbox', { name: '未完成任务' })).toBeDisabled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('never creates active HTML or image requests and only enables isolated absolute web links', () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const { container } = render(
      <MarkdownPreview
        content={[
          '<script>alert("private")</script>',
          '',
          '<iframe src="https://tracker.invalid/frame"></iframe>',
          '',
          '<img src="https://tracker.invalid/raw" onerror="alert(1)">',
          '',
          '<svg onload="alert(1)"></svg>',
          '',
          '<style>body { background: url(https://tracker.invalid/style); }</style>',
          '',
          '![私密图](https://tracker.invalid/image)',
          '',
          '[安全](https://example.com/path?q=1) [普通](http://example.com/)',
          '[脚本](javascript:alert%281%29) [实体](java&#x0A;script:alert%281%29)',
          '[数据](data:text/html;base64,SGk=) [文件](file:///etc/passwd)',
          '[Blob](blob:https://example.com/123) [邮件](mailto:owner@example.com)',
          '[相对](/api/v1/auth/logout) [协议相对](//tracker.invalid/)',
          '[凭据](https://user:password@tracker.invalid/)',
        ].join('\n')}
      />,
    );
    expect(
      container.querySelector(
        'script,style,iframe,img,svg,object,embed,video,audio',
      ),
    ).toBeNull();
    expect(
      screen.getByText('图片：私密图（请使用私密图库）'),
    ).toBeInTheDocument();
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(2);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      'https://example.com/path?q=1',
      'http://example.com/',
    ]);
    for (const link of links) {
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
      expect(link).toHaveAttribute('referrerpolicy', 'no-referrer');
    }
    expect(
      container.querySelector('[src], [srcset], [onerror], [onload]'),
    ).toBeNull();
    expect(screen.getByText('脚本').closest('a')).toBeNull();
    expect(screen.getByText('相对').closest('a')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('starts with the verbatim source and changes only display without submitting or fetching', () => {
    const source =
      '# 原文\r\n\r\n中文 e\u0301 和尾空格  \n<script>private()</script>\n';
    const submit = vi.fn((event) => event.preventDefault());
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const { container } = render(
      <form onSubmit={submit}>
        <MarkdownContent content={source} />
      </form>,
    );
    const toggle = screen.getByRole('button', { name: '预览 Markdown' });
    expect(toggle).toHaveAttribute('type', 'button');
    expect(container.querySelector('pre')?.textContent).toBe(source);
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(
      within(screen.getByLabelText('Markdown 内容预览')).getByRole('heading', {
        name: '原文',
      }),
    ).toBeInTheDocument();
    expect(container.querySelector('script')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '查看原文' }));
    expect(container.querySelector('pre')?.textContent).toBe(source);
    expect(submit).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });
});
