import { useState } from "react";
import { type Account, signIn, signUp } from "../auth";
import Panda from "./Panda";

/** Sign in, or create an account, with email and password. */
export default function SignIn({ onSignedIn }: { onSignedIn: (a: Account) => void }) {
  const [mode, setMode] = useState<"in" | "up">("in"),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [confirm, setConfirm] = useState(""),
    [name, setName] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const creating = mode === "up";
  async function submit() {
    if (creating && password !== confirm) {
      setError("The passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      onSignedIn(creating ? await signUp(email, password, name.trim()) : await signIn(email, password));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login">
      <p className="brand">
        <Panda size={28} /> Gehihi
      </p>
      <h1>Your private research workspace</h1>
      <p>Chat with your documents using OpenAI or Gemini.</p>
      <form
        className="auth-form"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <h2>{creating ? "Create an account" : "Sign in"}</h2>
        <label>
          Email
          <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        {creating && (
          <label>
            Name (optional)
            <input autoComplete="name" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        )}
        <label>
          Password
          <input
            type="password"
            autoComplete={creating ? "new-password" : "current-password"}
            required
            minLength={creating ? 10 : 1}
            maxLength={128}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {creating && <p className="state">At least 10 characters.</p>}
        {creating && (
          <label>
            Confirm password
            <input
              type="password"
              autoComplete="new-password"
              required
              maxLength={128}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </label>
        )}
        {error && <p role="alert">{error}</p>}
        <button className="primary" disabled={busy}>
          {busy ? "Please wait…" : creating ? "Create account" : "Sign in"}
        </button>
        <p>
          {creating ? "Already have an account? " : "New here? "}
          <button
            type="button"
            className="link"
            onClick={() => {
              setMode(creating ? "in" : "up");
              setConfirm("");
              setError("");
            }}
          >
            {creating ? "Sign in" : "Create an account"}
          </button>
        </p>
      </form>
    </main>
  );
}
