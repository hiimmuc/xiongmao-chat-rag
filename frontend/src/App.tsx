import { useEffect, useRef, useState } from "react";
import { all, api, json } from "./api";
import { type Account, restore, signOut } from "./auth";
import SignIn from "./components/SignIn";
import { apply, cached, DEFAULTS, type Prefs } from "./prefs";
import ChatPage from "./pages/ChatPage";
import AccountPage from "./pages/AccountPage";
import ProjectsPage, { type Project } from "./pages/ProjectsPage";
import SettingsPage from "./pages/SettingsPage";
import UsagePage from "./pages/UsagePage";
import { Icon, PATH } from "./components/Icon";
import { useDismiss } from "./hooks/useDismiss";
import Panda, { type Mood } from "./components/Panda";
const NAV = [
  ["projects", "Projects", PATH.folder],
  ["usage", "Usage", PATH.chart],
  ["account", "Account", PATH.user],
  ["settings", "Settings", PATH.gear],
] as const;
const route = () => location.pathname.slice(1) || "chat";
type Toast = { id: number; text: string };
/** Auth gate and application shell: workspace switcher, preferences, toasts and routing. */
export default function App() {
  const [user, setUser] = useState<Account | null>(),
    [page, setPage] = useState(route()),
    [navOpen, setNavOpen] = useState(false),
    [slot, setSlot] = useState<HTMLElement | null>(null),
    [projects, setProjects] = useState<Project[]>([]),
    [freeId, setFreeId] = useState(""),
    [fresh, setFresh] = useState(0),
    [happy, setHappy] = useState(false),
    [projectId, setProjectId] = useState(localStorage.getItem("project") || ""),
    [switcher, setSwitcher] = useState(false),
    [busy, setBusy] = useState(false),
    [prefs, setPrefs] = useState<Prefs>(cached),
    [toasts, setToasts] = useState<Toast[]>([]),
    [openReq, setOpenReq] = useState<{ id: string }>();
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;
  const go = (p: string) => {
    history.pushState({}, "", p === "chat" ? "/" : "/" + p);
    setPage(p);
    setNavOpen(false);
  };
  const toast = (text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => (t.some((x) => x.text === text) ? t : [...t.slice(-3), { id, text }]));
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  };
  // Honours the user's notification preferences; read through a ref so pollers never resubscribe.
  const notify = (kind: "document_processing" | "system", text: string) => {
    const n = prefsRef.current.notifications;
    if (n.enabled && n[kind]) toast(text);
  };
  async function loadProjects() {
    const { items, free_id } = await api<{ items: Project[]; free_id: string }>("/projects");
    setProjects(items);
    setFreeId(free_id);
    setProjectId((cur) => (cur === free_id || items.some((p) => p.id === cur) ? cur : items[0].id));
  }
  async function change(patch: Record<string, unknown>) {
    const before = prefsRef.current;
    const next = { ...before, ...patch, notifications: { ...before.notifications, ...(patch.notifications as object) } } as Prefs;
    prefsRef.current = next;
    setPrefs(next);
    apply(next);
    try {
      await api<Prefs>("/me/preferences", json("PATCH", patch));
      toast("Settings saved");
    } catch (e) {
      prefsRef.current = before;
      setPrefs(before);
      apply(before);
      toast("Could not save settings: " + (e as Error).message);
    }
  }
  const newChat = () => {
    setFresh((n) => n + 1);
    go("chat");
  };
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && !busy) {
      setHappy(true);
      const t = setTimeout(() => setHappy(false), 2200);
      return () => clearTimeout(t);
    }
    wasBusy.current = busy;
  }, [busy]);
  const mood: Mood = busy ? "thinking" : happy ? "happy" : "idle";
  function select(id: string) {
    if (busy) return toast("Wait for the current answer to finish before switching projects.");
    setProjectId(id);
    setSwitcher(false);
  }
  useEffect(() => {
    if (projectId) localStorage.setItem("project", projectId);
  }, [projectId]);
  useEffect(() => {
    const update = () => setPage(route());
    addEventListener("popstate", update);
    return () => removeEventListener("popstate", update);
  }, []);
  useDismiss(navOpen || switcher, () => {
    setNavOpen(false);
    setSwitcher(false);
  });
  useEffect(() => {
    if (prefs.mode !== "system") return;
    const media = matchMedia("(prefers-color-scheme: dark)");
    const update = () => apply(prefsRef.current);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [prefs.mode]);
  useEffect(() => {
    // A refresh cookie from an earlier visit signs the browser straight back in.
    void restore().then(setUser);
    // Reload on sign-out so nothing from this account stays in memory for the next one.
    const out = () => location.assign("/");
    addEventListener("auth:signed-out", out);
    return () => removeEventListener("auth:signed-out", out);
  }, []);
  const signedIn = Boolean(user);
  useEffect(() => {
    if (!signedIn) return;
    loadProjects().catch((e) => toast(String(e)));
    api<Prefs>("/me/preferences")
      .then((p) => {
        const full = { ...DEFAULTS, ...p };
        setPrefs(full);
        apply(full);
      })
      .catch(() => {});
  }, [signedIn]);
  useEffect(() => {
    // Free chats have no project-wide document list to watch.
    if (!signedIn || !projectId || !freeId || projectId === freeId) return;
    let live = true,
      timer: ReturnType<typeof setTimeout>;
    const known = new Map<string, string>();
    const tick = async () => {
      let pending = false;
      try {
        for (const d of await all<{ id: string; name: string; state: string }>(`/documents?project_id=${projectId}`)) {
          const was = known.get(d.id);
          if (was && was !== d.state && (d.state === "ready" || d.state === "failed"))
            notify("document_processing", d.state === "ready" ? `${d.name} is ready to use.` : `${d.name} could not be processed.`);
          known.set(d.id, d.state);
          if (d.state !== "ready" && d.state !== "failed") pending = true;
        }
      } catch {}
      if (live) timer = setTimeout(tick, pending ? 2500 : 6000);
    };
    void tick();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [signedIn, projectId, freeId]);
  if (user === undefined)
    return <main className="login" role="status">Loading your workspace…</main>;
  if (!user) return <SignIn onSignedIn={setUser} />;
  const known = NAV.some(([p]) => p === page);
  const active = projects.find((p) => p.id === projectId);
  return (
    <div className="shell" data-nav={navOpen ? "open" : "closed"}>
      <aside className="sidebar" id="sidebar" aria-label="Sidebar">
        <button className="brand-btn" onClick={newChat} aria-label="Gehihi, start a new chat">
          <Panda size={34} mood={mood} />
          <span className="brand">Gehihi</span>
        </button>
        <div className="switcher">
          <button
            className="project-btn"
            aria-haspopup="listbox"
            aria-expanded={switcher}
            aria-label={`Workspace: ${active?.name ?? (projectId === freeId ? "Free chats" : "Loading")}`}
            disabled={!freeId}
            onClick={() => setSwitcher(!switcher)}
          >
            <Icon d={PATH.folder} />
            <span>{active?.name ?? (projectId === freeId && freeId ? "Free chats" : "Loading…")}</span>
            <Icon d="M6 9l6 6 6-6" size={16} />
          </button>
          {switcher && (
            <>
              <div className="scrim-clear" onClick={() => setSwitcher(false)} />
              <div className="pop switch-pop" role="listbox" aria-label="Project">
                <button role="option" aria-selected={projectId === freeId} className="option" onClick={() => select(freeId)}>
                  Free chats
                  {projectId === freeId && <Icon d={PATH.check} />}
                </button>
                {projects.map((p) => (
                  <button key={p.id} role="option" aria-selected={p.id === projectId} className="option" onClick={() => select(p.id)}>
                    {p.name}
                    {p.id === projectId && <Icon d={PATH.check} />}
                  </button>
                ))}
                <button className="option manage" onClick={() => { setSwitcher(false); go("projects"); }}>
                  Manage projects
                </button>
              </div>
            </>
          )}
        </div>
        <div className="side-slot" ref={setSlot} />
        <nav className="side-nav" aria-label="Main">
          {NAV.map(([p, label, icon]) => (
            <button key={p} aria-current={page === p ? "page" : undefined} onClick={() => go(p)}>
              <Icon d={icon} />
              {label}
            </button>
          ))}
        </nav>
        <div className="side-foot">
          <button onClick={() => void signOut()}>Sign out</button>
        </div>
      </aside>
      <div className="scrim" onClick={() => setNavOpen(false)} />
      <div className="content">
        <div className="topbar">
          <button className="ghost menu-btn" aria-label="Open sidebar" aria-controls="sidebar" aria-expanded={navOpen} onClick={() => setNavOpen(true)}>
            <Icon d="M4 7h16M4 12h16M4 17h16" />
          </button>
          <button className="brand-btn" onClick={newChat} aria-label="Gehihi, start a new chat">
            <Panda size={28} mood={mood} />
            <span className="brand">Gehihi</span>
          </button>
        </div>
        <div className={"page" + (known ? "" : " chat")}>
          <div hidden={known} style={{ height: "100%" }}>
            {projectId && freeId && (
              <ChatPage
                slot={slot}
                active={!known}
                free={projectId === freeId}
                freeId={freeId}
                fresh={fresh}
                mood={mood}
                shortlist={prefs.models}
                openChat={() => go("chat")}
                request={openReq}
                projectId={projectId}
                notify={(_, text) => notify("system", text)}
                onBusy={setBusy}
              />
            )}
          </div>
          {page === "projects" && projectId && (
            <ProjectsPage
              projects={projects}
              projectId={projects.some((p) => p.id === projectId) ? projectId : ""}
              select={select}
              reload={loadProjects}
              openChat={(id) => {
                setOpenReq({ id });
                go("chat");
              }}
              newChat={newChat}
            />
          )}
          {page === "usage" && <UsagePage />}
          {page === "account" && <AccountPage user={user} />}
          {page === "settings" && <SettingsPage prefs={prefs} change={change} />}
        </div>
      </div>
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div className="toast" key={t.id}>
            {t.text}
            <button className="ghost" aria-label="Dismiss" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}>
              <Icon d="M6 6l12 12M18 6L6 18" size={16} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
