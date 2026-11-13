import { api } from "./api";
import type { Doc } from "./types";

export const ACCEPT = ".pdf,.txt,.md";
const MAX_BYTES = 10 * 1024 * 1024;

/**
 * Upload one file. Without `conversationId` it becomes a project document every chat in the
 * project can use; with one (free chats only) it belongs to that chat. Errors name the file.
 */
export async function uploadDocument(file: File, projectId: string, conversationId?: string) {
  if (!/\.(pdf|txt|md)$/i.test(file.name)) throw new Error(`${file.name}: use a text PDF, TXT or Markdown file`);
  if (file.size > MAX_BYTES) throw new Error(`${file.name}: larger than 10 MiB`);
  const body = new FormData();
  body.append("file", file);
  const query = `project_id=${projectId}` + (conversationId ? `&conversation_id=${conversationId}` : "");
  try {
    return await api<Doc>(`/documents?${query}`, { method: "POST", body });
  } catch (e) {
    throw new Error(`${file.name}: ${(e as Error).message}`);
  }
}

/** Still being stored or indexed. */
export const isWorking = (d: Doc) => ["uploading", "queued", "processing"].includes(d.state);
