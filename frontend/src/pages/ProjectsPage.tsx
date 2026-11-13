import { useEffect, useState } from "react";
import { all, api, json, remove } from "../api";
import ConfirmDialog from "../components/ConfirmDialog";
import DeletionNotice, { type Receipt } from "../components/DeletionNotice";
import { Icon, PATH } from "../components/Icon";
import ProjectDocuments from "../components/ProjectDocuments";
import RowMenu from "../components/RowMenu";
export type Project = { id: string; name: string; documents: number; conversations: number };
type Chat = { id: string; title: string };

/**
 * Projects on the left; the selected project's documents and chats on the right.
 * Selecting a project here only shows it. "Chat in this project" makes it the active workspace.
 */
export default function ProjectsPage({
  projects,
  projectId,
  select,
  reload,
  openChat,
  newChat,
}: {
  projects: Project[];
  projectId: string;
  select: (id: string) => void;
  reload: () => Promise<void>;
  openChat: (id: string) => void;
  newChat: () => void;
}) {
  const [name, setName] = useState(""),
    [viewing, setViewing] = useState(projectId),
    [renaming, setRenaming] = useState(false),
    [draft, setDraft] = useState(""),
    [confirm, setConfirm] = useState<Project>(),
    [receipt, setReceipt] = useState<Receipt>(),
    [error, setError] = useState(""),
    [chats, setChats] = useState<Chat[] | null>(null);
  const current = projects.find((p) => p.id === viewing) ?? projects.find((p) => p.id === projectId) ?? projects[0];
  const id = current?.id;

  useEffect(() => {
    void reload().catch(() => {}); // fresh document and chat counts
  }, []);
  useEffect(() => {
    if (!id) return;
    setChats(null);
    setRenaming(false);
    all<Chat>(`/conversations?project_id=${id}`)
      .then(setChats)
      .catch((e) => setError(e.message));
  }, [id]);

  async function run(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <main className="projects-page">
      <div className="usage-head">
        <h1>Projects</h1>
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            const n = name.trim();
            if (n)
              void run(async () => {
                const p = await api<Project>("/projects", json("POST", { name: n }));
                setName("");
                setViewing(p.id);
              });
          }}
        >
          <label className="sr-only" htmlFor="new-project">
            New project name
          </label>
          <input id="new-project" placeholder="New project name" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
          <button className="primary" disabled={!name.trim()}>
            Create project
          </button>
        </form>
      </div>
      <p className="note">Each project keeps its own documents, chats and search index. Nothing is shared between projects.</p>
      {error && <p role="alert">{error}</p>}
      {receipt && <DeletionNotice receipt={receipt} />}

      <div className="projects-layout">
        <nav className="project-list" aria-label="Your projects">
          {projects.map((p) => (
            <button key={p.id} className="project-item" aria-current={p.id === id || undefined} onClick={() => setViewing(p.id)}>
              <Icon d={PATH.folder} />
              <span className="project-name">
                <strong>{p.name}</strong>
                <small>
                  {p.documents} {p.documents === 1 ? "document" : "documents"} · {p.conversations} {p.conversations === 1 ? "chat" : "chats"}
                </small>
              </span>
              {p.id === projectId && <span className="active-tag">Active</span>}
            </button>
          ))}
        </nav>

        {current && (
          <div className="project-detail">
            <header className="detail-head">
              {renaming ? (
                <form
                  className="inline-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const n = draft.trim();
                    setRenaming(false);
                    if (n && n !== current.name) void run(() => api("/projects/" + current.id, json("PATCH", { name: n })));
                  }}
                >
                  <input aria-label="Project name" autoFocus maxLength={120} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Escape" && setRenaming(false)} />
                  <button className="primary">Save</button>
                  <button type="button" onClick={() => setRenaming(false)}>
                    Cancel
                  </button>
                </form>
              ) : (
                <div>
                  <h2>{current.name}</h2>
                  <p className="state">{current.id === projectId ? "Your active workspace" : "Not active. Chat in it to switch."}</p>
                </div>
              )}
              <div className="detail-actions">
                <button
                  className="primary"
                  onClick={() => {
                    select(current.id);
                    newChat();
                  }}
                >
                  <Icon d={PATH.plus} /> Chat in this project
                </button>
                <RowMenu
                  label={`Options for ${current.name}`}
                  items={[
                    {
                      label: "Rename",
                      icon: PATH.edit,
                      onSelect: () => {
                        setDraft(current.name);
                        setRenaming(true);
                      },
                    },
                    { label: "Delete", icon: PATH.trash, danger: true, disabled: projects.length < 2, onSelect: () => setConfirm(current) },
                  ]}
                />
              </div>
            </header>

            <ProjectDocuments projectId={current.id} onChange={() => void reload().catch(() => {})} />

            <section className="panel" aria-labelledby="chats-h">
              <div className="panel-head">
                <h2 id="chats-h">Chats</h2>
                {chats && chats.length > 0 && <span className="state">{chats.length} total</span>}
              </div>
              {chats === null && <p className="state" role="status">Loading chats…</p>}
              {chats?.length === 0 && <p className="state">No chats yet. Use “Chat in this project” to start one.</p>}
              {!!chats?.length && (
                <ul className="chat-links">
                  {chats.map((c) => (
                    <li key={c.id}>
                      <button
                        className="ghost"
                        onClick={() => {
                          select(current.id);
                          openChat(c.id);
                        }}
                      >
                        <Icon d={PATH.open} size={16} />
                        <span>{c.title}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}
      </div>

      {confirm && (
        <ConfirmDialog
          title="Delete project?"
          body={`“${confirm.name}” and all of its documents, chats and search data will be deleted. Access is blocked immediately; cleanup runs in the background. This cannot be undone.`}
          action="Delete project"
          cancel={() => setConfirm(undefined)}
          confirm={() => {
            const p = confirm;
            setConfirm(undefined);
            void run(async () => {
              setReceipt(await remove("/projects/" + p.id));
              const next = projects.find((x) => x.id !== p.id)!.id;
              setViewing(next);
              if (p.id === projectId) select(next);
            });
          }}
        />
      )}
    </main>
  );
}
