export function PinnedBadge({ isPinned }: { isPinned: boolean }) {
  return isPinned ? <span className="pinned-badge">已置顶</span> : null;
}
