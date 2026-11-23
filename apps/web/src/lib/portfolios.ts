// Browser client for saved portfolios (`/api/compute/portfolios`). The session
// cookie goes along automatically (same origin). Mirrors
// apps/compute/sextant_compute/portfolio/saved.py.

import { getMessages } from "@/i18n";
import { computePath } from "./compute";
import type { ApiErrorBody } from "./envelope";

export type SavedHolding = { ticker: string; quantity: number; cost_price: number; currency: string };

export type PortfolioSummary = { id: string; name: string; created_at: string; updated_at: string };

export type SavedPortfolio = PortfolioSummary & { holdings: SavedHolding[] };

/** What create and update send. Numbers are null when the input is empty or not a number, so the API reports the field. */
export type PortfolioBody = {
  name: string;
  holdings: { ticker: string; quantity: number | null; cost_price: number | null; currency: string }[];
};

export type PortfolioOutcome<T> =
  | { kind: "ok"; value: T }
  | { kind: "invalid"; message: string; fields: Record<string, string> }
  | { kind: "failed"; message: string };

/** `suffix` follows `/portfolios`: "" for the collection, `/<id>` for one portfolio. */
async function send<T>(method: string, suffix: "" | `/${string}`, body?: unknown): Promise<PortfolioOutcome<T>> {
  const t = getMessages().common.errors;
  let res: Response;
  try {
    res = await fetch(computePath(`/portfolios${suffix}`), {
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

export const portfoliosApi = {
  list: () => send<PortfolioSummary[]>("GET", ""),
  get: (id: string) => send<SavedPortfolio>("GET", `/${id}`),
  create: (body: PortfolioBody) => send<SavedPortfolio>("POST", "", body),
  update: (id: string, body: PortfolioBody) => send<SavedPortfolio>("PUT", `/${id}`, body),
  remove: (id: string) => send<void>("DELETE", `/${id}`),
};
