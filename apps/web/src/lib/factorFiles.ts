// Browser client for the signed-in user's own factor files
// (`/api/compute/risk/factor-files`, apps/compute/sextant_compute/risk/factor_api.py).
// ADR 0003: Sextant ships no real factor data; a user uploads a Kenneth R. French
// Data Library CSV and Risk & Performance on My data regresses on it, for that user only.

import { send as sendJson } from "./computeClient";

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

/** Errors are one message: the file's own (its field) when there is one. */
async function send<T>(method: string, suffix: "" | `/${FactorFileKind}`, body?: unknown): Promise<FactorOutcome<T>> {
  const outcome = await sendJson<T>(method, `/risk/factor-files${suffix}`, body);
  if (outcome.kind === "invalid") return { kind: "failed", message: outcome.fields.file ?? outcome.message };
  return outcome;
}

export const factorFilesApi = {
  list: () => send<FactorFile[]>("GET", ""),
  upload: (filename: string, csv: string) => send<FactorFile>("POST", "", { filename, csv }),
  remove: (kind: FactorFileKind) => send<void>("DELETE", `/${kind}`),
};
