import { accessToken, base, forget, restore } from "./auth";
export { base };
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(
      (requestId ? `${message} (request ${requestId})` : message) +
        (code === "deletion_outcome_unknown"
          ? ". Deletion may still proceed. Keep this request ID and retry the same action in this browser session; the original deletion key is retained."
          : ""),
    );
  }
}
/** Authenticated fetch against the API; throws ApiError with the server's code and request ID.
 *  A 401 renews the access token once and retries; if that fails the app returns to sign-in. */
export async function request(path: string, options: RequestInit = {}, retried = false): Promise<Response> {
  const token = await accessToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(base + path, { ...options, headers });
  if (response.status === 401 && !retried) {
    if (await restore()) return request(path, options, true);
    forget();
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({
      code: "request_failed",
      message: `Request failed (${response.status})`,
    }));
    throw new ApiError(error.code, error.message, error.request_id);
  }
  return response;
}
export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const r = await request(path, options);
  return r.status === 204 ? (undefined as T) : r.json();
}
export const json = (method: string, body: unknown) => ({
  method,
  body: JSON.stringify(body),
});
/** DELETE with an idempotency key kept for the session, so a retry replays the same request. */
export async function remove(path: string, body?: unknown) {
  const key = sessionStorage.getItem("deletion:" + path) || crypto.randomUUID();
  sessionStorage.setItem("deletion:" + path, key);
  return api(path, {
    method: "DELETE",
    headers: { "Idempotency-Key": key },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
/** Follow `next_cursor` to collect every page of a list endpoint. */
export async function all<T>(path: string): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | null = null;
  do {
    const result: { items: T[]; next_cursor: string | null } = await api(
      path +
        (path.includes("?") ? "&" : "?") +
        (cursor ? "cursor=" + encodeURIComponent(cursor) : ""),
    );
    items.push(...result.items);
    cursor = result.next_cursor;
  } while (cursor);
  return items;
}
