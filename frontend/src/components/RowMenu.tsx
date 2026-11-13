import { useEffect, useRef, useState } from "react";
import { useDismiss } from "../hooks/useDismiss";
import { Icon, PATH } from "./Icon";

export type MenuItem = { label: string; icon: string; onSelect: () => void; danger?: boolean; disabled?: boolean };

/** Three-dot button that opens a floating action list beside it. */
export default function RowMenu({ label, items, className = "" }: { label: string; items: MenuItem[]; className?: string }) {
  const [at, setAt] = useState<{ x: number; y: number }>();
  const popup = useRef<HTMLDivElement>(null);
  const close = () => setAt(undefined);
  useDismiss(!!at, close, popup);
  useEffect(() => {
    if (!at) return;
    addEventListener("resize", close);
    return () => removeEventListener("resize", close);
  }, [at]);

  return (
    <>
      <button
        className={"kebab " + className}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={!!at}
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setAt(at ? undefined : { x: Math.min(r.right + 6, innerWidth - 200), y: Math.min(r.top, innerHeight - 20 - items.length * 48) });
        }}
      >
        <Icon d={PATH.more} />
      </button>
      {at && (
        <div ref={popup} className="pop menu-pop" role="menu" style={{ left: at.x, top: at.y }}>
          {items.map((item) => (
            <button
              key={item.label}
              role="menuitem"
              className={item.danger ? "danger" : undefined}
              disabled={item.disabled}
              onClick={() => {
                close();
                item.onSelect();
              }}
            >
              <Icon d={item.icon} /> {item.label}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
