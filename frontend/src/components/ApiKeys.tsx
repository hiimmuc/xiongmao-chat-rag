import { useEffect, useState } from "react";
import { api, json } from "../api";
import { providerName } from "../format";

type KeyStatus = { provider: string; source: "own" | "shared" | "none"; hint: string | null };
type Result = { ok: boolean; message: string };

/** Per-provider key management: shows which key is in effect, tests it, replaces or removes your own. */
export default function ApiKeys() {
  const [items, setItems] = useState<KeyStatus[]>();
  const [enabled, setEnabled] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ items: KeyStatus[]; storage_enabled: boolean }>("/me/keys")
      .then((r) => {
        setItems(r.items);
        setEnabled(r.storage_enabled);
      })
      .catch((e) => setError(e.message));
  }, []);

  const replace = (next: KeyStatus) => setItems((all) => all?.map((i) => (i.provider === next.provider ? next : i)));

  return (
    <section>
      <h2>API keys</h2>
      <p className="note">Use your own provider keys for your chats and document search. Without one, the shared key set by the operator is used. Keys are stored encrypted and are never shown again.</p>
      {error && <p role="alert">{error}</p>}
      {!items && !error && (
        <p className="state" role="status">
          Loading keys…
        </p>
      )}
      {!enabled && <p className="note">Saving personal keys is not enabled on this server. You can still test a key.</p>}
      {items?.map((item) => (
        <KeyCard key={item.provider} item={item} canSave={enabled} onChange={replace} />
      ))}
    </section>
  );
}

function KeyCard({ item, canSave, onChange }: { item: KeyStatus; canSave: boolean; onChange: (s: KeyStatus) => void }) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>();
  const path = `/me/keys/${item.provider}`;
  const name = providerName(item.provider);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setResult(undefined);
    try {
      await action();
    } catch (e) {
      setResult({ ok: false, message: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const test = () => run(async () => setResult(await api<Result>(path + "/test", json("POST", draft ? { api_key: draft } : {}))));
  const save = () =>
    run(async () => {
      onChange(await api<KeyStatus>(path, json("PUT", { api_key: draft })));
      setDraft("");
      setResult({ ok: true, message: "Key saved" });
    });
  const remove = () =>
    run(async () => {
      onChange(await api<KeyStatus>(path, { method: "DELETE" }));
      setResult({ ok: true, message: "Key removed" });
    });

  return (
    <div className="key-card">
      <div className="key-head">
        <strong>{name}</strong>
        <span className="state">
          {item.source === "own" ? `Your key ending ${item.hint}` : item.source === "shared" ? "Using the shared key" : "No key configured"}
        </span>
      </div>
      <label>
        {name} API key
        <input type="password" autoComplete="off" spellCheck={false} placeholder="Paste a key to test or replace" value={draft} onChange={(e) => setDraft(e.target.value)} />
      </label>
      <div className="key-actions">
        <button disabled={busy || (!draft && item.source === "none")} onClick={() => void test()}>
          Test connection
        </button>
        <button className="primary" disabled={busy || !canSave || draft.length < 8} onClick={() => void save()}>
          Save key
        </button>
        {item.source === "own" && (
          <button className="danger" disabled={busy} onClick={() => void remove()}>
            Remove
          </button>
        )}
      </div>
      {result && (
        <p className={result.ok ? "key-result ok" : "key-result"} role="status">
          {result.message}
        </p>
      )}
    </div>
  );
}
