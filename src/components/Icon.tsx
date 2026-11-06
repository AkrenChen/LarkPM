export default function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    board: <><rect x="3" y="4" width="7" height="16" rx="1.5"/><rect x="14" y="4" width="7" height="10" rx="1.5"/></>,
    person: <><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></>,
    gantt: <><path d="M5 3v18h17M8 6h7M8 11h12M13 16h7"/></>,
    sync: <><path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5"/></>,
    settings: <><path d="m9 3-1 3-3 1v4l-2 1 2 3v3l4 1 1 2h4l1-2 4-1v-3l2-3-2-1V7l-3-1-1-3z"/><circle cx="12" cy="12" r="3"/></>,
    keyboard: <><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 12h.01M10 12h.01M14 12h.01M18 12h.01M7 16h10"/></>,
    plus: <path d="M12 5v14M5 12h14"/>, search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></>,
    chevron: <path d="m9 5 7 7-7 7"/>, check: <path d="m5 12 4 4L19 6"/>, close: <path d="m6 6 12 12M18 6 6 18"/>,
    link: <><path d="m10 13 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0" transform="translate(0 1) scale(.95)"/></>,
    branch: <><circle cx="6" cy="4" r="2"/><circle cx="18" cy="10" r="2"/><circle cx="6" cy="20" r="2"/><path d="M6 6v12M8 15h4a6 6 0 0 0 6-3"/></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>, calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M7 3v4M17 3v4"/></>,
    alert: <><path d="m12 3 10 18H2z"/><path d="M12 9v5m0 3v.1"/></>, box: <><path d="m12 3 9 5v9l-9 5-9-5V8zM3 8l9 5 9-5M12 13v9"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.box}</svg>;
}
