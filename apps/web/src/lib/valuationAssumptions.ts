// Browser client for saved valuation assumptions (`/api/compute/valuation/assumptions`).
// The session cookie goes along automatically (same origin). Mirrors
// apps/compute/sextant_compute/valuation/saved.py.

import { getMessages } from "@/i18n";
import { computePath } from "./compute";
import type { ApiErrorBody } from "./envelope";

/** `ValuationAssumptions`: rates as decimals, null = derive (or no price). */
export type ValuationAssumptions = {
  forecast_years: number;
  growth_rate: number;
  terminal_growth: number;
  discount_rate: number | null;
  risk_free_rate: number;
  beta: number;
  equity_risk_premium: number;
  cost_of_equity: number | null;
  cost_of_debt: number | null;
  tax_rate: number | null;
  debt_weight: number | null;
  share_price: number | null;
};

export type AssumptionSet = {
  id: string;
  ticker: string;
  name: string;
  assumptions: ValuationAssumptions;
  created_at: string;
  updated_at: string;
};

/** Numbers are null when the input is empty or not a number, so the API reports the field. */
export type AssumptionSetBody = {
  ticker: string;
  name: string;
  assumptions: Record<keyof ValuationAssumptions, number | null>;
};

export type AssumptionsOutcome<T> =
  | { kind: "ok"; value: T }
  | { kind: "signedOut" }
  | { kind: "invalid"; message: string; fields: Record<string, string> }
  | { kind: "failed"; message: string };

async function send<T>(
  method: string,
  suffix: string,
  body?: unknown,
): Promise<AssumptionsOutcome<T>> {
  const t = getMessages().common.errors;
  let res: Response;
  try {
    res = await fetch(computePath(`/valuation/assumptions${suffix}`), {
      method,
      headers:
        body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return { kind: "failed", message: t.computeUnavailable };
  }
  if (res.status === 401) return { kind: "signedOut" };
  if (res.status === 204) return { kind: "ok", value: undefined as T };
  const json: unknown = await res.json().catch(() => null);
  if (res.ok && json !== null) return { kind: "ok", value: json as T };
  if (json && typeof json === "object" && "error" in json) {
    const { error } = json as ApiErrorBody;
    if (Object.keys(error.fields ?? {}).length > 0)
      return { kind: "invalid", message: error.message, fields: error.fields };
    return { kind: "failed", message: error.message };
  }
  return { kind: "failed", message: t.computeUnavailable };
}

export const valuationAssumptionsApi = {
  list: (ticker: string) =>
    send<AssumptionSet[]>("GET", `?ticker=${encodeURIComponent(ticker)}`),
  save: (body: AssumptionSetBody) => send<AssumptionSet>("POST", "", body),
  remove: (id: string) => send<void>("DELETE", `/${id}`),
};
