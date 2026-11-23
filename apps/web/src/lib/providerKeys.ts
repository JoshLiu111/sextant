// Browser client for the user's own provider keys (`/api/compute/keys`). The
// session cookie goes along automatically (same origin). Mirrors
// apps/compute/sextant_compute/keys/api.py. The plaintext key is only ever sent,
// never received: responses carry the last four characters (`hint`).

import { send as sendJson, type Outcome } from "./computeClient";

/**
 * The provider registry (mirrors `MY_DATA_SOURCES` in
 * apps/compute/sextant_compute/data/sources.py): every provider a user can save a
 * key for, with its display name, in the order Settings lists them. Each one
 * backs My data (`myData.ts`); a new provider is one line here.
 */
export const PROVIDER_NAMES = { tiingo: "Tiingo", fmp: "FMP" } as const;

export type Provider = keyof typeof PROVIDER_NAMES;

export const PROVIDERS = Object.keys(PROVIDER_NAMES) as Provider[];

export type SavedKey = { provider: Provider; hint: string; created_at: string; updated_at: string };

export type KeyOutcome<T> = Outcome<T>;

function send<T>(method: string, suffix: "" | `/${Provider}`, body?: unknown): Promise<KeyOutcome<T>> {
  return sendJson<T>(method, `/keys${suffix}`, body);
}

export const providerKeysApi = {
  list: () => send<SavedKey[]>("GET", ""),
  save: (provider: Provider, key: string) => send<SavedKey>("PUT", `/${provider}`, { key }),
  remove: (provider: Provider) => send<void>("DELETE", `/${provider}`),
};
