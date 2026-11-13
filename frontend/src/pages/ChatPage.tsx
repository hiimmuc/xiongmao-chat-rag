import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { all, api, json, remove, request } from "../api";
import { Icon, PATH } from "../components/Icon";
import ChatSidebar from "../components/ChatSidebar";
import CitationDialog from "../components/CitationDialog";
import Composer from "../components/Composer";
import ConfirmDialog from "../components/ConfirmDialog";
import DeletionNotice, { type Receipt } from "../components/DeletionNotice";
import MessageItem from "../components/MessageItem";
import Panda, { type Mood } from "../components/Panda";
import Thinking from "../components/Thinking";
import { useChatDocuments } from "../hooks/useChatDocuments";
import { useFileDrop } from "../hooks/useFileDrop";
import { applyEvent, readEvents } from "../stream";
import type { Chat, Message, Model, Source } from "../types";

const PENDING = ["accepted", "queued", "pending", "running", "streaming"];

type Props = {
  slot: HTMLElement | null;
  active: boolean;
  projectId: string;
  freeId: string;
  free: boolean;
  fresh: number;
  mood: Mood;
  shortlist: string[];
  request?: { id: string };
  openChat: () => void;
  notify: (kind: "system", text: string) => void;
  onBusy: (busy: boolean) => void;
};

/** The chat workspace: sidebar list in the shell, message stream and composer here. */
export default function ChatPage({ slot, active: visible, projectId, freeId, free, fresh, mood, shortlist, request: wanted, openChat, notify, onBusy }: Props) {
  const [chats, setChats] = useState<Chat[]>([]);
  const [chat, setChat] = useState<Chat>();
  const [models, setModels] = useState<Model[]>([]);
  const [model, setModel] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [search, setSearch] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState<Source>();
  const [receipt, setReceipt] = useState<Receipt>();
  const [loadingChats, setLoadingChats] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [copied, setCopied] = useState("");
  const [toDelete, setToDelete] = useState<Chat>();
  const [away, setAway] = useState(false);
  const field = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const running = useRef<string>(undefined);
  const stream = useRef<AbortController>(undefined);
  const selected = useRef<string>(undefined);

  const documents = useChatDocuments({ free, freeId, projectId, chat, setChat, ensureChat: create, visible, onError: setError });
  const drop = useFileDrop((files) => void documents.upload(files), !busy);
  const shown = shortlist.length ? models.filter((m) => shortlist.includes(m.id) || m.id === model) : models;
  const modelLabel = (id?: string) => models.find((m) => m.id === id)?.label || id || "Model";
  const latestAnswer = [...messages].reverse().find((m) => m.role === "assistant");

  async function list() {
    try {
      setChats(await all<Chat>(`/conversations?project_id=${projectId}&search=${encodeURIComponent(search)}`));
    } finally {
      setLoadingChats(false);
    }
  }

  function reset() {
    selected.current = undefined;
    setChat(undefined);
    setMessages([]);
    documents.clearPending();
    setError("");
  }

  async function open(c: Pick<Chat, "id">) {
    if (busy) return;
    selected.current = c.id;
    setLoadingMessages(true);
    openChat();
    try {
      const [detail, history] = await Promise.all([api<Chat>("/conversations/" + c.id), all<Message>("/conversations/" + c.id + "/messages")]);
      if (selected.current === c.id) {
        setChat(detail);
        setMessages(history);
        setError("");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingMessages(false);
    }
  }

  async function create(title = "New chat") {
    try {
      const c = await api<Chat>("/conversations", json("POST", { title, project_id: projectId }));
      const ids = documents.takePending();
      if (ids.length) c.document_ids = (await api<Chat>("/conversations/" + c.id, json("PATCH", { document_ids: ids }))).document_ids;
      await list();
      await open(c);
      return c;
    } catch (e) {
      setError((e as Error).message);
    }
  }

  /** Reload saved messages until the generation reaches a terminal state. */
  async function reconcile(id: string, chatId: string) {
    let g;
    do {
      g = await api("/generations/" + id);
      if (selected.current === chatId) setMessages(await all<Message>("/conversations/" + chatId + "/messages"));
      if (!PENDING.includes(g.status)) break;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    } while (selected.current === chatId);
  }

  async function send(retryOf?: string) {
    if (busy || !model || (!retryOf && !text.trim())) return;
    setBusy(true);
    setError("");
    let c = chat;
    let answer: string | undefined;
    try {
      c ??= await create(text.trim().replace(/\s+/g, " ").slice(0, 48) || "New chat");
      if (!c) return;
      const chatId = c.id;
      selected.current = chatId;
      const message = text;
      if (!retryOf) {
        setText("");
        setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", content: message }]);
      }
      stream.current = new AbortController();
      const body = retryOf ? { retry_of: retryOf } : { message };
      const r = await request("/conversations/" + chatId + "/generations", {
        ...json("POST", { request_id: crypto.randomUUID(), model_id: model, ...body }),
        signal: stream.current.signal,
      });
      if (!r.headers.get("Content-Type")?.includes("text/event-stream")) {
        answer = (await r.json()).generation_id;
        running.current = answer;
        await reconcile(answer!, chatId);
        return;
      }
      let terminal = false;
      for await (const e of readEvents(r.body!)) {
        if (e.event === "start") {
          answer = String(e.data.generation_id);
          running.current = answer;
        }
        const id = answer;
        setMessages((m) => applyEvent(m, e, id, model));
        if (e.event === "done") terminal = true;
        if (e.event === "error") {
          terminal = true;
          if (e.data.generation_id) answer = String(e.data.generation_id);
          const reason = String(e.data.message || "Generation failed");
          setError(reason);
          notify("system", reason);
        }
      }
      if (answer) await reconcile(answer, chatId);
      if (!terminal) setError("Connection interrupted. The saved attempt has been reloaded.");
      await list();
    } catch (e) {
      if (answer && c) await reconcile(answer, c.id).catch(() => {});
      setError((e as Error).name === "AbortError" ? "Stream disconnected; reload this conversation to check the saved result." : (e as Error).message);
    } finally {
      setBusy(false);
      running.current = undefined;
    }
  }

  async function stop() {
    if (!running.current) return;
    try {
      await api("/generations/" + running.current + "/cancel", { method: "POST" });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function rename(c: Chat, title: string) {
    try {
      const next = await api<Chat>("/conversations/" + c.id, json("PATCH", { title }));
      if (chat?.id === c.id) setChat(next);
      await list();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function deleteChat(c: Chat) {
    setToDelete(undefined);
    try {
      setReceipt(await remove("/conversations/" + c.id));
      if (chat?.id === c.id) reset();
      await list();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function branch(m: Message) {
    if (!chat) return;
    try {
      const c = await api<Chat>("/conversations/" + chat.id + "/branch", json("POST", { message_id: m.id }));
      await list();
      await open(c);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function copy(m: Message) {
    try {
      await navigator.clipboard.writeText(m.content);
      setCopied(m.id);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      setError("Copy failed. Select the text and copy it manually.");
    }
  }

  async function showSource(m: Message, s: Source) {
    try {
      setSource(await api<Source>(`/generations/${m.generation_id}/citations/${s.id}`));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    api("/models")
      .then((r) => {
        setModels(r.items);
        setModel(r.items[0]?.id || "");
      })
      .catch((e) => setError(e.message));
    return () => stream.current?.abort();
  }, []);

  useEffect(() => {
    // A workspace switch starts clean; nothing from the previous one stays on screen.
    reset();
    setChats([]);
    setLoadingChats(true);
  }, [projectId]);

  useEffect(() => {
    list().catch((e) => setError(e.message));
  }, [search, projectId]);

  useEffect(() => {
    if (models.length && !models.some((m) => m.id === model)) {
      setModel((shortlist.length ? models.find((m) => shortlist.includes(m.id)) : undefined)?.id ?? models[0].id);
    }
  }, [models, shortlist]);

  useEffect(() => {
    if (fresh && !busy) {
      reset();
      openChat();
    }
  }, [fresh]);

  useEffect(() => onBusy(busy), [busy]);

  useEffect(() => {
    if (wanted) void open(wanted);
  }, [wanted]);

  useEffect(() => {
    if (!busy && visible) field.current?.focus();
  }, [busy, visible, chat?.id]);

  useEffect(() => {
    // A hidden page measures 0; sizing then would collapse the box to nothing.
    const t = field.current;
    if (t && t.scrollHeight > 0) {
      t.style.height = "auto";
      t.style.height = Math.min(t.scrollHeight, 200) + "px";
    }
  }, [text, visible]);

  // Follow new content only while the reader is at the bottom; otherwise offer a jump.
  useEffect(() => {
    if (atBottom.current) end.current?.scrollIntoView({ block: "end" });
    else setAway(true);
  }, [messages]);

  useEffect(() => {
    atBottom.current = true;
    setAway(false);
  }, [chat?.id]);

  const empty = !messages.length && !loadingMessages;

  return (
    <>
      {slot &&
        createPortal(
          <ChatSidebar
            chats={chats}
            current={chat}
            loading={loadingChats}
            busy={busy}
            search={search}
            onSearch={setSearch}
            onNew={() => {
              reset();
              openChat();
            }}
            onOpen={(c) => void open(c)}
            onRename={(c, title) => void rename(c, title)}
            onDelete={setToDelete}
          />,
          slot,
        )}
      <main className={"chat-main" + (empty ? " is-empty" : "")} {...drop.props}>
        {drop.over && (
          <div className="drop-overlay" aria-hidden="true">
            <Icon d={PATH.file} size={36} />
            <strong>Drop files to add them</strong>
            <span>{free ? "They belong to this chat only." : "They are saved to this project's documents and used in this chat."}</span>
            <small>Text PDF, TXT or Markdown, up to 10 MiB each</small>
          </div>
        )}
        <div className="chat-head">
          <h1>{chat?.title || "New chat"}</h1>
        </div>
        <section
          className="messages"
          aria-label="Conversation"
          aria-live="polite"
          onScroll={(e) => {
            const el = e.currentTarget;
            atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
            if (atBottom.current) setAway(false);
          }}
        >
          <div className="column">
            {error && <p role="alert">{error}</p>}
            {receipt && <DeletionNotice receipt={receipt} />}
            {loadingMessages && (
              <p className="state" role="status">
                Loading messages…
              </p>
            )}
            {empty && (
              <div className="empty">
                <Panda size={96} mood={mood} />
                <h2>What would you like to work through?</h2>
                <p>Ask a question, or drop PDF, TXT or Markdown files here for answers with citations.</p>
              </div>
            )}
            {messages.map((m) => (
              <MessageItem
                key={m.id}
                message={m}
                label={modelLabel(m.model_id)}
                isLatestAnswer={m.id === latestAnswer?.id}
                busy={busy}
                canBranch={!!chat}
                copied={copied === m.id}
                onCopy={() => void copy(m)}
                onRegenerate={() => void send(m.generation_id)}
                onBranch={() => void branch(m)}
                onSource={(s) => void showSource(m, s)}
              />
            ))}
            {busy && messages[messages.length - 1]?.role === "user" && (
              <article className="message assistant">
                <div className="message-meta">
                  <span>{modelLabel(model)}</span>
                </div>
                <div className="bubble">
                  <Thinking />
                </div>
              </article>
            )}
            <div ref={end} />
          </div>
        </section>
        {away && (
          <button
            className="jump icon-btn"
            aria-label="Jump to latest messages"
            title="Jump to latest"
            onClick={() => {
              atBottom.current = true;
              setAway(false);
              end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
            }}
          >
            <Icon d={PATH.down} />
          </button>
        )}
        <Composer
          field={field}
          text={text}
          setText={setText}
          busy={busy}
          onSend={() => void send()}
          onStop={() => void stop()}
          free={free}
          docs={documents.docs}
          chosen={documents.chosen}
          onToggleDoc={(id, on) => void documents.toggle(id, on)}
          uploading={documents.uploading}
          onUpload={(files) => void documents.upload(files)}
          models={shown}
          model={model}
          onModel={setModel}
          showStarters={empty && documents.chosen.length > 0}
        />
      </main>
      {toDelete && (
        <ConfirmDialog
          title="Delete chat?"
          body={`“${toDelete.title}” will be deleted. Access is blocked immediately; cleanup runs in the background.`}
          action="Delete"
          cancel={() => setToDelete(undefined)}
          confirm={() => void deleteChat(toDelete)}
        />
      )}
      {source && <CitationDialog source={source} close={() => setSource(undefined)} />}
    </>
  );
}
