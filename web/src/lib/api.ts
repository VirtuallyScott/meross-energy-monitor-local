/** Thin client for the Energy Hub API envelope (API-002) with CSRF handling (AUTH-008). */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

interface Envelope<T> {
  data: T;
  error: { code: string; message: string; request_id?: string } | null;
  meta: Record<string, unknown>;
}

const BASE = "/api/v1";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function csrfToken(): string | undefined {
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith("ehub_csrf="))
    ?.slice("ehub_csrf=".length);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body !== undefined) headers.set("content-type", "application/json");
  const csrf = csrfToken();
  if (UNSAFE.has(method) && csrf) headers.set("x-csrf-token", csrf);

  const response = await fetch(BASE + path, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 204) return undefined as T;
  let body: Envelope<T> | undefined;
  try {
    body = (await response.json()) as Envelope<T>;
  } catch {
    throw new ApiError(response.status, "bad_response", "The server sent an unreadable reply.");
  }
  if (!response.ok || body.error) {
    const err = body.error ?? { code: "http_error", message: response.statusText };
    throw new ApiError(response.status, err.code, err.message);
  }
  return body.data;
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const put = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(body) });

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
