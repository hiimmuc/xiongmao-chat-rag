import { useEffect, type RefObject } from "react";

/** Calls `onDismiss` on Escape, or on a press outside `inside` when a ref is given, while `active`. */
export function useDismiss(active: boolean, onDismiss: () => void, inside?: RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!active) return;
    const escape = (e: KeyboardEvent) => e.key === "Escape" && onDismiss();
    const outside = (e: MouseEvent) => inside && !inside.current?.contains(e.target as Node) && onDismiss();
    addEventListener("keydown", escape);
    addEventListener("mousedown", outside);
    return () => {
      removeEventListener("keydown", escape);
      removeEventListener("mousedown", outside);
    };
  }, [active]);
}
