// The fetch-and-classify step every browser client of a signed-in compute API
// shares (saved portfolios, provider keys, saved valuation assumptions, factor
// files). The session cookie goes along automatically (same origin).

import { getMessages } from "@/i18n";
import { computePath } from "./compute";
import type { ApiErrorBody } from "./envelope";

/** A compute API call's result: the body, field errors to show inline, or a message. */
export type Outcome<T> =
  | { kind: "ok"; value: T }
  | { kind: "invalid"; message: string; fields: Record<string, string> }
  | { kind: "failed"; message: string };

/** `Outcome`, plus `signed_out` for a 401 (the caller shows a sign-in prompt instead of an error). */
export type SignedInOutcome<T> = Outcome<T> | { kind: "signed_out" };

async function request<T>(
  method: string,
  path: `/${string}`,
  body: unknown,
  signedOut: boolean,
): Promise<SignedInOutcome<T>> {
  const t = getMessages().common.errors;
  let res: Response;
  try {
    res = await fetch(computePath(path), {
      method,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return { kind: "failed", message: t.computeUnavailable };
  }
  if (signedOut && res.status === 401) return { kind: "signed_out" };
  if (res.status === 204) return { kind: "ok", value: undefined as T };
  const json: unknown = await res.json().catch(() => null);
  if (res.ok && json !== null) return { kind: "ok", value: json as T };
  if (json && typeof json === "object" && "error" in json) {
    const { error } = json as ApiErrorBody;
    if (Object.keys(error.fields ?? {}).length > 0) return { kind: "invalid", message: error.message, fields: error.fields };
    return { kind: "failed", message: error.message };
  }
  return { kind: "failed", message: t.computeUnavailable };
}

/** `method` `path` (under `/api/compute`) with an optional JSON `body`; a 401 is an ordinary failure. */
export function send<T>(method: string, path: `/${string}`, body?: unknown): Promise<Outcome<T>> {
  return request<T>(method, path, body, false) as Promise<Outcome<T>>;
}

/** `send`, but a 401 answers `{ kind: "signed_out" }`. */
export function sendSignedIn<T>(method: string, path: `/${string}`, body?: unknown): Promise<SignedInOutcome<T>> {
  return request<T>(method, path, body, true);
}
