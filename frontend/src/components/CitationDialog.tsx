import { useEffect, useRef } from "react";
import type { Source } from "../types";

export default function CitationDialog({ source, close }: { source: Source; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog ref={dialog} onClose={close} aria-label="Citation">
      <h2>{source.name}</h2>
      <p>{source.page && `Page ${source.page}`}</p>
      <pre>{source.snippet || "Source deleted or unavailable."}</pre>
      <button autoFocus onClick={() => dialog.current?.close()}>
        Close
      </button>
    </dialog>
  );
}
