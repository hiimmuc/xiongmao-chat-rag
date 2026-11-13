import { useState } from "react";
import type { Chat } from "../types";
import { Icon, PATH } from "./Icon";
import RowMenu from "./RowMenu";

type Props = {
  chats: Chat[];
  current?: Chat;
  loading: boolean;
  busy: boolean;
  search: string;
  onSearch: (value: string) => void;
  onNew: () => void;
  onOpen: (chat: Chat) => void;
  onRename: (chat: Chat, title: string) => void;
  onDelete: (chat: Chat) => void;
};

/** New chat, title search and the recent-chat list with a per-chat rename and delete menu. */
export default function ChatSidebar({ chats, current, loading, busy, search, onSearch, onNew, onOpen, onRename, onDelete }: Props) {
  const [renaming, setRenaming] = useState<Chat>();
  const [draft, setDraft] = useState("");

  function commitRename() {
    const chat = renaming;
    setRenaming(undefined);
    const title = draft.trim();
    if (chat && title && title !== chat.title) onRename(chat, title);
  }

  return (
    <>
      <button className="new-chat" disabled={busy} onClick={onNew}>
        <Icon d={PATH.plus} />
        New chat
      </button>
      <div className="search">
        <Icon d={PATH.search} size={16} />
        <label className="sr-only" htmlFor="chat-search">
          Search chats
        </label>
        <input id="chat-search" type="search" placeholder="Search chats" value={search} onChange={(e) => onSearch(e.target.value)} />
      </div>
      <p className="side-title">Recent</p>
      <div className="chat-list">
        {loading && (
          <p className="state" role="status">
            Loading chats…
          </p>
        )}
        {chats.map((c) => (
          <div className="chat-row" key={c.id} data-active={current?.id === c.id || undefined}>
            {renaming?.id === c.id ? (
              <input
                className="rename"
                aria-label="Chat title"
                autoFocus
                maxLength={120}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onFocus={(e) => e.target.select()}
                onBlur={commitRename}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitRename();
                  if (e.key === "Escape") setRenaming(undefined);
                }}
              />
            ) : (
              <>
                <button className="chat-item" disabled={busy} aria-current={current?.id === c.id ? "page" : undefined} onClick={() => onOpen(c)}>
                  {c.title}
                </button>
                <RowMenu
                  className="chat-more"
                  label={`Options for ${c.title}`}
                  items={[
                    {
                      label: "Rename",
                      icon: PATH.edit,
                      onSelect: () => {
                        setDraft(c.title);
                        setRenaming(c);
                      },
                    },
                    { label: "Delete", icon: PATH.trash, danger: true, onSelect: () => onDelete(c) },
                  ]}
                />
              </>
            )}
          </div>
        ))}
        {!loading && !chats.length && <p className="state">{search ? "No chats match." : "No chats yet. Send a message to start one."}</p>}
      </div>
    </>
  );
}
