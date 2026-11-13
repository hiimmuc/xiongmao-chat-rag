import { useEffect, useState } from "react";
import { all, api, json } from "../api";
import { isWorking, uploadDocument } from "../documents";
import type { Chat, Doc } from "../types";

type Options = {
  free: boolean;
  freeId: string;
  projectId: string;
  chat?: Chat;
  setChat: (chat: Chat) => void;
  ensureChat: () => Promise<Chat | undefined>;
  visible: boolean;
  onError: (message: string) => void;
};

/**
 * Documents a chat can use, and uploads made from the chat.
 *
 * Project chat: an upload becomes a project document (listed on the Projects page and usable by
 * every chat in the project). Free chat: an upload belongs to that chat only. Either way, a file
 * uploaded here is switched on for this chat as soon as it is ready.
 */
export function useChatDocuments({ free, freeId, projectId, chat, setChat, ensureChat, visible, onError }: Options) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [pending, setPending] = useState<string[]>([]);
  const [incoming, setIncoming] = useState<string[]>([]); // uploaded here, not ready yet
  const url = free ? (chat ? `/documents?project_id=${freeId}&conversation_id=${chat.id}` : "") : `/documents?project_id=${projectId}`;
  const watching = free || incoming.length > 0;

  useEffect(() => {
    setDocs([]);
    setPending([]);
    setIncoming([]);
  }, [projectId]);

  useEffect(() => {
    if (!visible) return;
    if (!url) return setDocs([]);
    const load = () => all<Doc>(url).then(setDocs).catch((e) => onError(e.message));
    void load();
    if (!watching) return;
    const timer = setInterval(() => void load(), 2500);
    return () => clearInterval(timer);
  }, [visible, url, watching]);

  useEffect(() => {
    const done = docs.filter((d) => incoming.includes(d.id) && !isWorking(d));
    if (!done.length) return;
    setIncoming((x) => x.filter((id) => !done.some((d) => d.id === id)));
    done.filter((d) => d.state === "failed").forEach((d) => onError(`${d.name} could not be processed.`));
    const ready = done.filter((d) => d.state === "ready").map((d) => d.id);
    if (!ready.length) return;
    if (!chat) return setPending((p) => [...new Set([...p, ...ready])]);
    const document_ids = [...new Set([...chat.document_ids, ...ready])];
    api<Chat>("/conversations/" + chat.id, json("PATCH", { document_ids })).then(setChat).catch((e) => onError(e.message));
  }, [docs]);

  const chosen = chat ? chat.document_ids : pending;

  async function toggle(id: string, on: boolean) {
    const next = on ? [...chosen, id] : chosen.filter((x) => x !== id);
    if (!chat) return setPending(next);
    try {
      setChat(await api<Chat>("/conversations/" + chat.id, json("PATCH", { document_ids: next })));
    } catch (e) {
      onError((e as Error).message);
    }
  }

  async function upload(files: File[]) {
    // Free-chat files need the chat to exist; create it once for the whole batch.
    const target = free ? (chat ?? (await ensureChat())) : undefined;
    if (free && !target) return;
    for (const file of files) {
      try {
        const doc = await uploadDocument(file, free ? freeId : projectId, target?.id);
        setIncoming((x) => [...x, doc.id]);
        setDocs((x) => [...x, doc]);
      } catch (e) {
        onError((e as Error).message);
      }
    }
  }

  /** Selections made before the first message; returned once so a new chat can adopt them. */
  function takePending() {
    const ids = pending;
    setPending([]);
    return ids;
  }

  const uploading = docs.filter((d) => incoming.includes(d.id));
  return { docs, chosen, uploading, toggle, upload, takePending, clearPending: () => setPending([]) };
}
