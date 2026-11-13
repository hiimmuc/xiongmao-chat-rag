import { useEffect, useState } from "react";
import { api } from "../api";
export type Receipt = {
  deletion_id: string;
  status: string;
  error_code?: string;
};
export default function DeletionNotice({ receipt }: { receipt: Receipt }) {
  const [status, setStatus] = useState(receipt),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    setStatus(receipt);
    async function poll() {
      try {
        const next = await api<Receipt>("/deletions/" + receipt.deletion_id);
        if (!live) return;
        setStatus(next);
        setError("");
        if (!["completed", "failed"].includes(next.status))
          timer = setTimeout(poll, 3000);
      } catch (e) {
        if (live) setError((e as Error).message);
      }
    }
    void poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [receipt]);
  return (
    <p role="status">
      Deletion {receipt.deletion_id}: {status.status}.{" "}
      {status.status === "completed"
        ? "Physical cleanup completed."
        : "Access is blocked after acceptance; physical cleanup runs in the background."}
      {status.error_code &&
        ` ${status.error_code}. Contact support with the receipt.`}
      {error && ` Status unavailable: ${error}`}
    </p>
  );
}
