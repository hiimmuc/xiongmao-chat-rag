import { useEffect, useState } from "react";
import { api } from "../api";
import ApiKeys from "../components/ApiKeys";
import { STYLES, THEMES, type Prefs } from "../prefs";
const TABS = ["General", "Appearance", "Personalization", "Models", "API keys"] as const;
const SWATCH: Record<string, [string, string, string]> = {
  default: ["#fafafa", "#1c1c1a", "#0f766e"],
  github: ["#ffffff", "#1f2328", "#0969da"],
  claude: ["#faf9f5", "#29261f", "#ad4f2c"],
  gemini: ["#ffffff", "#1f1f1f", "#1a73e8"],
  monokai: ["#272822", "#f8f8f2", "#a6e22e"],
};
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);
function Seg<T extends string>({ label, value, options, set }: { label: string; value: T; options: [T, string][]; set: (v: T) => void }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={v} role="radio" aria-checked={value === v} aria-pressed={value === v} onClick={() => set(v)}>
          {text}
        </button>
      ))}
    </div>
  );
}
/** Appearance, notifications, personalization, models and API keys; each change saves at once. */
export default function SettingsPage({ prefs, change }: { prefs: Prefs; change: (patch: Record<string, unknown>) => Promise<void> }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>("General");
  const n = prefs.notifications;
  const [catalog, setCatalog] = useState<{ id: string; label: string; provider: string }[] | null>(null),
    [policyUrl, setPolicyUrl] = useState("");
  useEffect(() => {
    api("/models")
      .then((r) => {
        setCatalog(r.items);
        setPolicyUrl(r.processing_policy_url ?? "");
      })
      .catch(() => setCatalog([]));
  }, []);
  const picked = prefs.models;
  const flip = (id: string, on: boolean) => {
    const base = picked.length ? picked : (catalog ?? []).map((m) => m.id);
    const next = on ? [...new Set([...base, id])] : base.filter((x) => x !== id);
    // Everything ticked is stored as an empty list, which means "show all".
    void change({ models: next.length === (catalog ?? []).length ? [] : next });
  };
  const toggle = (key: keyof Prefs["notifications"], label: string, hint: string, off = false) => (
    <label className="switch-row">
      <span>
        {label}
        <small>{hint}</small>
      </span>
      <input type="checkbox" role="switch" checked={n[key]} disabled={off} onChange={(e) => void change({ notifications: { [key]: e.target.checked } })} />
    </label>
  );
  return (
    <main className="narrow">
      <h1>Settings</h1>
      <div className="seg tabs" role="tablist" aria-label="Settings sections">
        {TABS.map((t) => (
          <button key={t} role="tab" id={"tab-" + t} aria-selected={tab === t} aria-controls="panel" onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>
      <div id="panel" role="tabpanel" aria-labelledby={"tab-" + tab} className="settings">
        {tab === "Appearance" && (
          <>
            <section>
              <h2>Mode</h2>
              <Seg label="Mode" value={prefs.mode} set={(v) => void change({ mode: v })} options={[["light", "Light"], ["dark", "Dark"], ["system", "System"]]} />
            </section>
            <section>
              <h2>Color theme</h2>
              <div className="themes" role="radiogroup" aria-label="Color theme">
                {THEMES.map((t) => (
                  <button key={t} role="radio" aria-checked={prefs.color_theme === t} className="theme" onClick={() => void change({ color_theme: t })}>
                    <span className="swatch" aria-hidden="true" style={{ background: SWATCH[t][0], color: SWATCH[t][1] }}>
                      Aa
                      <i style={{ background: SWATCH[t][2] }} />
                    </span>
                    {cap(t)}
                  </button>
                ))}
              </div>
            </section>
            <section>
              <h2>Font family</h2>
              <Seg label="Font family" value={prefs.font_family} set={(v) => void change({ font_family: v })} options={[["system", "System"], ["sans", "Sans serif"], ["serif", "Serif"], ["mono", "Monospace"]]} />
            </section>
            <section>
              <h2>Font size</h2>
              <Seg label="Font size" value={prefs.font_size} set={(v) => void change({ font_size: v })} options={[["small", "Small"], ["medium", "Medium"], ["large", "Large"]]} />
            </section>
          </>
        )}
        {tab === "General" && (
          <>
          <section>
            <h2>Notifications</h2>
            <p className="note">Shown inside the app as short messages.</p>
            {toggle("enabled", "Enable notifications", "Turn all in-app notifications on or off.")}
            {toggle("document_processing", "Document processing", "When a document finishes indexing or fails.", !n.enabled)}
            {toggle("system", "System", "When an answer fails or a request is rejected.", !n.enabled)}
          </section>
          <section>
            <h2>Data processing</h2>
            <p className="note">
              Message text and retrieved document passages go to the provider of the model you select. Document and
              question text used for search always goes to the service's embedding provider, whichever model you chat with.
              {policyUrl && (
                <>
                  {" "}
                  <a href={policyUrl} target="_blank" rel="noreferrer">
                    Provider processing information
                  </a>
                </>
              )}
            </p>
          </section>
          </>
        )}
        {tab === "API keys" && <ApiKeys />}
        {tab === "Models" && (
          <section>
            <h2>Model shortlist</h2>
            <p className="note">Choose the models that appear in the chat picker. Select none to show all.</p>
            {catalog === null && <p className="state" role="status">Loading models…</p>}
            {[...new Set((catalog ?? []).map((m) => m.provider))].map((p) => (
              <fieldset className="model-group" key={p}>
                <legend>{p === "openai" ? "OpenAI" : p === "gemini" ? "Gemini" : p}</legend>
                {(catalog ?? [])
                  .filter((m) => m.provider === p)
                  .map((m) => (
                    <label className="switch-row" key={m.id}>
                      <span>{m.label}</span>
                      <input type="checkbox" role="switch" checked={!picked.length || picked.includes(m.id)} onChange={(e) => flip(m.id, e.target.checked)} />
                    </label>
                  ))}
              </fieldset>
            ))}
          </section>
        )}
        {tab === "Personalization" && (
          <section>
            <h2>Response style</h2>
            <p className="note">Changes how the assistant writes in every conversation. Grounding and citation rules for documents always apply.</p>
            <div className="styles" role="radiogroup" aria-label="Response style">
              {STYLES.map(([v, label, hint]) => (
                <button key={v} role="radio" aria-checked={prefs.response_style === v} className="style" onClick={() => void change({ response_style: v })}>
                  <strong>{label}</strong>
                  <small>{hint}</small>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
