type MarkdownEditorProps = {
  id: string;
  value: string;
  disabled?: boolean;
  onChange: (markdown: string) => void;
  onComposing: (composing: boolean) => void;
};

/** The adapter boundary stores Markdown verbatim; no HTML or editor document format. */
export function MarkdownEditor({
  id,
  value,
  disabled,
  onChange,
  onComposing,
}: MarkdownEditorProps) {
  return (
    <textarea
      id={id}
      className="markdown-editor"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onCompositionStart={() => onComposing(true)}
      onCompositionEnd={(event) => {
        onChange(event.currentTarget.value);
        onComposing(false);
      }}
      disabled={disabled}
      maxLength={100_000}
      rows={7}
      required
      spellCheck={false}
      autoComplete="off"
      placeholder="今天，有什么想留下的？支持 Markdown 原文。"
      aria-describedby={`${id}-hint`}
    />
  );
}
