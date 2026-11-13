export const Icon = ({ d, fill, size = 18 }: { d: string; fill?: boolean; size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" fill={fill ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);
export const PATH = {
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  retry: "M20 12a8 8 0 11-2.4-5.7M20 4v5h-5",
  branch: "M6 3v12M18 9a3 3 0 100-6 3 3 0 000 6zM6 21a3 3 0 100-6 3 3 0 000 6zM18 9a9 9 0 01-9 9",
  send: "M12 19V5M5 12l7-7 7 7",
  chevron: "M6 9l6 6 6-6",
  down: "M12 5v14M5 12l7 7 7-7",
  open: "M5 12h14M13 6l6 6-6 6",
  panel: "M4 5h16v14H4zM9 5v14",
  plus: "M12 5v14M5 12h14",
  search: "M11 4a7 7 0 100 14 7 7 0 000-14zM21 21l-4.3-4.3",
  more: "M12 5a1 1 0 100 2 1 1 0 000-2zM12 11a1 1 0 100 2 1 1 0 000-2zM12 17a1 1 0 100 2 1 1 0 000-2z",
  edit: "M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  file: "M7 3h7l5 5v13H7V3zM14 3v5h5",
  chart: "M5 20V10M12 20V4M19 20v-7",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0",
  folder: "M3 6a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V6z",
  gear: "M12 15a3 3 0 100-6 3 3 0 000 6zM19 12a7 7 0 00-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 00-2-1.2L14.2 3h-4l-.4 2.6a7 7 0 00-2 1.2l-2.3-.9-2 3.4 2 1.5a7 7 0 000 2.4l-2 1.5 2 3.4 2.3-.9a7 7 0 002 1.2l.4 2.6h4l.4-2.6a7 7 0 002-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z",
  check: "M5 12l5 5L20 7",
};
