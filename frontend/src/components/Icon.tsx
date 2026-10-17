// Biểu tượng lấy từ thiết kế (docs/design/Main.dc.html), nét 2px, 18×18.
const PATHS = {
  overview: (
    <>
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </>
  ),
  staff: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" />
      <path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c2 .7 3.2 2.5 3.5 5.2" />
    </>
  ),
  leads: <path d="M3 4h18l-7 8v6l-4 2v-8z" />,
  pages: (
    <>
      <path d="M4 4h16v16H4z" />
      <path d="M4 9h16M9 9v11" />
    </>
  ),
  ads: (
    <>
      <path d="M3 11l15-6v14L3 13z" />
      <path d="M7 13v5" />
    </>
  ),
  inbox: <path d="M4 5h16v11H8l-4 4z" />,
  bm: (
    <>
      <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" />
      <path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" />
    </>
  ),
  logout: (
    <>
      <path d="M15 4h4v16h-4" />
      <path d="M10 8l-4 4 4 4M6 12h10" />
    </>
  ),
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name }: { name: IconName }) {
  return (
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      {PATHS[name]}
    </svg>
  );
}
