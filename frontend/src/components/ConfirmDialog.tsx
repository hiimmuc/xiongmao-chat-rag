import { useEffect, useRef } from "react";
export default function ConfirmDialog({
  title,
  body,
  action,
  cancel,
  confirm,
}: {
  title: string;
  body: string;
  action: string;
  cancel: () => void;
  confirm: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog ref={dialog} onClose={cancel} aria-label={title}>
      <h2>{title}</h2>
      <p>{body}</p>
      <div className="dialog-actions">
        <button autoFocus onClick={() => dialog.current?.close()}>
          Cancel
        </button>
        <button className="primary danger-fill" onClick={confirm}>
          {action}
        </button>
      </div>
    </dialog>
  );
}
