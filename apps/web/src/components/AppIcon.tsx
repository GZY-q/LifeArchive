import type { ReactNode } from 'react';

const shapes = {
  journal: (
    <>
      <path d="M5 3h12a2 2 0 0 1 2 2v16H7a3 3 0 0 1-3-3V4a1 1 0 0 1 1-1Z" />
      <path d="M4 17h15M8 7h7M8 11h5" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="3" />
      <path d="M7 3v4m10-4v4M3 11h18M8 15h1m6 0h1m-8 3h1" />
    </>
  ),
  archive: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m16 16 5 5" />
    </>
  ),
  trash: (
    <>
      <path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7" />
    </>
  ),
  tags: (
    <>
      <path d="m3 4 8-1 10 10-8 8L3 11V4Z" />
      <circle cx="7.5" cy="7.5" r="1" />
    </>
  ),
  export: (
    <>
      <path d="M12 3v12m-4-4 4 4 4-4M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="10" width="14" height="11" rx="3" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export function AppIcon({ name }: { name: keyof typeof shapes }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {shapes[name]}
    </svg>
  );
}
