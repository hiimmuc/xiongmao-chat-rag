import { useEffect, useState } from "react";
import { api, ApiError, json, remove } from "../api";
import { type Account, changePassword, signOut } from "../auth";
/** Profile, password change and account deletion. */
export default function AccountPage({ user }: { user: Account }) {
  const [name, setName] = useState(""),
    [message, setMessage] = useState(""),
    [current, setCurrent] = useState(""),
    [next, setNext] = useState(""),
    [nextAgain, setNextAgain] = useState(""),
    [passwordMessage, setPasswordMessage] = useState(""),
    [confirmPassword, setConfirmPassword] = useState(""),
    [deleteMessage, setDeleteMessage] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    api("/me")
      .then((m) => setName(m.display_name || ""))
      .catch((e) => setMessage(e.message));
  }, []);
  async function save() {
    setBusy(true);
    try {
      await api("/me", json("PATCH", { display_name: name }));
      setMessage("Display name saved.");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function updatePassword() {
    if (next !== nextAgain) {
      setPasswordMessage("The new passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await changePassword(current, next);
      setCurrent("");
      setNext("");
      setNextAgain("");
      setPasswordMessage("Password changed. Other browsers have been signed out.");
    } catch (e) {
      setPasswordMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function del() {
    if (
      !confirm(
        "Delete your account, conversations, files and usage records? This cannot be undone. Accepted requests block access immediately; physical cleanup is performed in the background.",
      )
    )
      return;
    setBusy(true);
    try {
      const receipt = await remove("/me", { password: confirmPassword });
      sessionStorage.setItem("account-deletion-receipt", JSON.stringify(receipt));
      alert(`Account deletion accepted. Receipt: ${receipt.deletion_id}. Cleanup continues in the background.`);
      await signOut();
    } catch (e) {
      if (e instanceof ApiError && e.code === "wrong_password") setDeleteMessage("The password is not correct.");
      else
        setDeleteMessage(
          `${(e as Error).message}. If the outcome is unknown, retain the request ID and retry this action with the same browser session.`,
        );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="narrow">
      <h1>Account</h1>
      <p className="account-email">Signed in as {user.email}</p>
      <section className="panel" aria-labelledby="profile-title">
        <h2 id="profile-title">Profile</h2>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <label>
            Display name
            <input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
          </label>
          <button className="primary" disabled={busy}>Save name</button>
          {message && <p role="status" className="state">{message}</p>}
        </form>
      </section>
      <section className="panel" aria-labelledby="password-title">
        <h2 id="password-title">Change password</h2>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            void updatePassword();
          }}
        >
          <label>
            Current password
            <input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
          </label>
          <label>
            New password
            <input type="password" autoComplete="new-password" required minLength={10} maxLength={128} value={next} onChange={(e) => setNext(e.target.value)} />
            <span className="hint">At least 10 characters. Other browsers are signed out.</span>
          </label>
          <label>
            Confirm new password
            <input type="password" autoComplete="new-password" required maxLength={128} value={nextAgain} onChange={(e) => setNextAgain(e.target.value)} />
          </label>
          <button disabled={busy}>Change password</button>
          {passwordMessage && <p role="status" className="state">{passwordMessage}</p>}
        </form>
      </section>
      <section className="panel danger-zone" aria-labelledby="delete-title">
        <h2 id="delete-title">Delete account</h2>
        <p>
          Deletion removes your data and identity. Background cleanup and backup
          retention apply; externally processed content follows provider policies.
        </p>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            void del();
          }}
        >
          <label>
            Confirm with your password
            <input type="password" autoComplete="current-password" required value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
          </label>
          <button className="danger" disabled={busy}>Delete my account</button>
          {deleteMessage && <p role="alert" className="state">{deleteMessage}</p>}
        </form>
      </section>
    </main>
  );
}
