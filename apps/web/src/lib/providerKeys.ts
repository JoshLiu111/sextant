// Browser client for the user's own provider keys (`/api/compute/keys`). The
// session cookie goes along automatically (same origin). Mirrors
// apps/compute/sextant_compute/keys/api.py. The plaintext key is only ever sent,
// never received: responses carry the last four characters (`hint`).

import { getMessages } from "@/i18n";
import { computePath } from "./compute";
import type { ApiErrorBody } from "./envelope";

/** Every provider a user can save a key for, in the order Settings lists them. */
export const PROVIDERS = ["tiingo", "fmp"] as const;

export type Provider = (typeof PROVIDERS)[number];

export type SavedKey = { provider: Provider; hint: string; created_at: string; updated_at: string };

export type KeyOutcome<T> =
  | { kind: "ok"; value: T }
  | { kind: "invalid"; message: string; fields: Record<string, string> }
  | { kind: "failed"; message: string };

async function send<T>(method: string, suffix: "" | `/${Provider}`, body?: unknown): Promise<KeyOutcome<T>> {
  const t = getMessages().common.errors;
  let res: Response;
  try {
    res = await fetch(computePath(`/keys${suffix}`), {
      method,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return { kind: "failed", message: t.computeUnavailable };
  }
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

export const providerKeysApi = {
  list: () => send<SavedKey[]>("GET", ""),
  save: (provider: Provider, key: string) => send<SavedKey>("PUT", `/${provider}`, { key }),
  remove: (provider: Provider) => send<void>("DELETE", `/${provider}`),
};
