import type { TagLabel } from '../api/tags';

export function TagBadges({ tags }: { tags: TagLabel[] }) {
  if (!tags.length) return null;
  return (
    <ul className="tag-badges" aria-label="日记标签">
      {tags.map((tag) => (
        <li key={tag.id}>{tag.name}</li>
      ))}
    </ul>
  );
}
