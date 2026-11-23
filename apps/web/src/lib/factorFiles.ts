// Browser client for the signed-in user's own factor files
// (`/api/compute/risk/factor-files`, apps/compute/sextant_compute/risk/factor_api.py).
// ADR 0003: Sextant ships no real factor data; a user uploads a Kenneth R. French
// Data Library CSV and Risk & Performance on My data regresses on it, for that user only.

import { getMessages } from "@/i18n";
import { computePath } from "./compute";
import type { ApiErrorBody } from "./envelope";

export type FactorFileKind = "three_factor" | "momentum";

export type FactorFile = {
  kind: FactorFileKind;
  filename: string;
  frequency: "daily" | "monthly";
  /** `YYYY-MM` for monthly files, `YYYY-MM-DD` for daily. */
  first: string;
  last: string;
  periods: number;
  columns: string[];
  uploaded_at: string;
};

export type FactorOutcome<T> = { kind: "ok"; value: T } | { kind: "failed"; message: string };

async function send<T>(method: string, suffix: "" | `/${FactorFileKind}`, body?: unknown): Promise<FactorOutcome<T>> {
  const t = getMessages().common.errors;
  let res: Response;
  try {
    res = await fetch(computePath(`/risk/factor-files${suffix}`), {
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
    return { kind: "failed", message: error.fields?.file ?? error.message };
  }
  return { kind: "failed", message: t.computeUnavailable };
}

export const factorFilesApi = {
  list: () => send<FactorFile[]>("GET", ""),
  upload: (filename: string, csv: string) => send<FactorFile>("POST", "", { filename, csv }),
  remove: (kind: FactorFileKind) => send<void>("DELETE", `/${kind}`),
};
