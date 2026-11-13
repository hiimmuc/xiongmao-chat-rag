/**
 * Email and password sign-in against the backend's /auth routes.
 *
 * The access token (a JWT, valid for minutes) lives only in this module's memory, so page scripts
 * cannot find it in storage. The refresh token is an httpOnly cookie the browser sends to /auth
 * by itself; `restore()` uses it to get a new access token after a reload or when one expires.
 */
// Production builds set VITE_API_URL. Locally the API is on port 8000 of the same host as the page
// (localhost or 127.0.0.1), which keeps the refresh cookie same-site either way.
export const base =
  import.meta.env.VITE_API_URL || `${location.protocol}//${location.hostname}:8000/api/v1`;

export type Account = { id: string; email: string | null; display_name: string };
type Session = { access_token: string; expires_in: number; user: Account };

let token: string | null = null,
  expiresAt = 0,
  pending: Promise<Account | null> | null = null;

function keep(s: Session) {
  token = s.access_token;
  expiresAt = Date.now() + (s.expires_in - 30) * 1000; // renew 30 s early
  return s.user;
}

async function post(path: string, body?: unknown, headers: Record<string, string> = {}) {
  const r = await fetch(base + path, {
    method: "POST",
    credentials: "include",
    headers: body ? { "Content-Type": "application/json", ...headers } : headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    const detail = Array.isArray(e.detail) ? "Check the email and password (at least 10 characters)." : "";
    throw new Error(detail || e.message || `Request failed (${r.status})`);
  }
  return r.status === 204 ? null : r.json();
}

export async function signIn(email: string, password: string) {
  return keep(await post("/auth/login", { email, password }));
}

export async function signUp(email: string, password: string, display_name?: string) {
  return keep(await post("/auth/signup", { email, password, display_name: display_name || undefined }));
}

/** Use the refresh cookie for a new access token. Resolves to null when signed out. */
export function restore(): Promise<Account | null> {
  pending ??= post("/auth/refresh")
    .then(keep)
    .catch(() => {
      token = null;
      return null;
    })
    .finally(() => (pending = null));
  return pending;
}

/** A valid access token, renewing it first if needed; null when signed out. */
export async function accessToken() {
  if (token && Date.now() < expiresAt) return token;
  return (await restore()) ? token : null;
}

export async function changePassword(current_password: string, new_password: string) {
  const t = await accessToken();
  return keep(await post("/auth/password", { current_password, new_password }, { Authorization: `Bearer ${t}` }));
}

/** Forget the session here and on the server, then tell the app. */
export async function signOut() {
  await post("/auth/logout").catch(() => {});
  forget();
}

export function forget() {
  token = null;
  dispatchEvent(new Event("auth:signed-out"));
}
