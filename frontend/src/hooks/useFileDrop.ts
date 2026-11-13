import { useRef, useState, type DragEvent } from "react";

/**
 * Drag-and-drop of files onto an element: spread `props` on it and use `over` to show a hint.
 * Only file drags react; dragging text or links around the page is ignored.
 */
export function useFileDrop(onFiles: (files: File[]) => void, enabled = true) {
  const [over, setOver] = useState(false);
  const depth = useRef(0); // dragenter/leave also fire for children, so count them
  const files = (e: DragEvent) => enabled && e.dataTransfer.types.includes("Files");
  return {
    over,
    props: {
      onDragEnter(e: DragEvent) {
        if (!files(e)) return;
        e.preventDefault();
        depth.current++;
        setOver(true);
      },
      onDragOver(e: DragEvent) {
        if (!files(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      },
      onDragLeave(e: DragEvent) {
        if (!files(e)) return;
        depth.current = Math.max(0, depth.current - 1);
        if (!depth.current) setOver(false);
      },
      onDrop(e: DragEvent) {
        if (!files(e)) return;
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        onFiles([...e.dataTransfer.files]);
      },
    },
  };
}
