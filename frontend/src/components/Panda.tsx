import { useEffect, useRef, useState } from "react";
export type Mood = "idle" | "thinking" | "happy";
// Flat panda: pupils follow the pointer, blink on a timer, wiggle on click; thinking looks up, happy squints.
export default function Panda({ size = 32, mood = "idle", label, onClick }: { size?: number; mood?: Mood; label?: string; onClick?: () => void }) {
  const svg = useRef<SVGSVGElement>(null);
  const [wiggle, setWiggle] = useState(false);
  useEffect(() => {
    let frame = 0;
    const move = (e: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const el = svg.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        const dx = e.clientX - (r.left + r.width / 2),
          dy = e.clientY - (r.top + r.height / 2);
        const d = Math.hypot(dx, dy) || 1,
          k = Math.min(1, d / 160) * 3;
        el.style.setProperty("--px", ((dx / d) * k).toFixed(2));
        el.style.setProperty("--py", ((dy / d) * k).toFixed(2));
      });
    };
    addEventListener("pointermove", move);
    return () => {
      removeEventListener("pointermove", move);
      cancelAnimationFrame(frame);
    };
  }, []);
  const art = (
    <svg
      ref={svg}
      className={"panda " + mood + (wiggle ? " wiggle" : "")}
      width={size}
      height={size}
      viewBox="0 0 120 120"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      onAnimationEnd={() => setWiggle(false)}
    >
      <g className="ears" fill="#1c1c1a">
        <circle cx="27" cy="27" r="15" />
        <circle cx="93" cy="27" r="15" />
      </g>
      <g className="head">
        <ellipse cx="60" cy="66" rx="45" ry="39" fill="#fff" stroke="#1c1c1a" strokeWidth="3" />
        <ellipse cx="41" cy="62" rx="12" ry="15" fill="#1c1c1a" transform="rotate(22 41 62)" />
        <ellipse cx="79" cy="62" rx="12" ry="15" fill="#1c1c1a" transform="rotate(-22 79 62)" />
        {mood === "happy" ? (
          <g fill="none" stroke="#fff" strokeWidth="3.5" strokeLinecap="round">
            <path d="M35 62q6-7 12 0" />
            <path d="M73 62q6-7 12 0" />
          </g>
        ) : (
          <g className="eyes">
            <circle cx="42" cy="62" r="6.5" fill="#fff" />
            <circle cx="78" cy="62" r="6.5" fill="#fff" />
            <g className="pupils" fill="#1c1c1a">
              <circle cx="42" cy="62" r="3.4" />
              <circle cx="78" cy="62" r="3.4" />
            </g>
          </g>
        )}
        <ellipse cx="60" cy="79" rx="6" ry="4.2" fill="#1c1c1a" />
        <path d="M60 83v4M52 89q8 6 16 0" fill="none" stroke="#1c1c1a" strokeWidth="2.6" strokeLinecap="round" />
      </g>
    </svg>
  );
  return onClick ? (
    <button type="button" className="panda-btn" onClick={() => { setWiggle(true); onClick(); }} aria-label={label}>
      {art}
    </button>
  ) : (
    <span className="panda-btn static" onPointerEnter={() => setWiggle(true)}>
      {art}
    </span>
  );
}
