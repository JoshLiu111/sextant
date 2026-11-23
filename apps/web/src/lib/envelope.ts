// The unified result envelope returned by every compute endpoint, and the
// browser-side client that calls one. Mirrors apps/compute/sextant_compute/envelope.py
// and apps/compute/sextant_compute/errors.py.

import { getMessages } from "@/i18n";
import { computePath } from "./compute";

export type MetricStatus = "ok" | "missing_data" | "error";

/** Units the compute service attaches to metrics and series; see `formatValue`. */
export type Unit =
  | "currency"
  | "decimal"
  | "per_dollar"
  | "per_vol_point"
  | "per_day"
  | "per_rate_point"
  | "date"
  | (string & {});

export type MetricResult = {
  value: number | null;
  status: MetricStatus;
  reason: string | null;
  unit: Unit | null;
  /** Extra facts about an ok value, e.g. a max drawdown's `peak` / `trough` ISO dates. */
  details: Record<string, string | number | null>;
};

export type SeriesPoint = { x: number | string; y: number | null };

export type SeriesResult = {
  status: MetricStatus;
  reason: string | null;
  x_unit: Unit | null;
  y_unit: Unit | null;
  points: SeriesPoint[];
};

export type DataSource = { id: string; name: string; is_demo: boolean };

export type ResultEnvelope<M extends string = string, S extends string = string> = {
  calculation_id: string;
  tool: string;
  metrics: Record<M, MetricResult>;
  series: Record<S, SeriesResult>;
  source: DataSource;
  meta: {
    parameters: Record<string, unknown>;
    computed_at: string;
    data_cutoff: string | null;
  };
};

/** Body of every non-2xx compute response. */
export type ApiErrorBody = {
  error: { code: string; message: string; fields: Record<string, string> };
};

export type ComputeOutcome<M extends string = string, S extends string = string> =
  | { kind: "ok"; result: ResultEnvelope<M, S> }
  | { kind: "invalid"; message: string; fields: Record<string, string> }
  | { kind: "failed"; message: string };

function isApiError(body: unknown): body is ApiErrorBody {
  return typeof body === "object" && body !== null && "error" in body;
}

/**
 * POST a request model to a compute endpoint from the browser.
 * Never throws for HTTP or network failures; returns a `ComputeOutcome` instead.
 * Rethrows AbortError so callers can ignore superseded requests.
 */
export async function postCompute<M extends string, S extends string>(
  path: `/${string}`,
  body: unknown,
  signal?: AbortSignal,
): Promise<ComputeOutcome<M, S>> {
  const t = getMessages().common.errors;
  let res: Response;
  try {
    res = await fetch(computePath(path), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (signal?.aborted) throw err;
    return { kind: "failed", message: t.computeUnavailable };
  }
  const json: unknown = await res.json().catch(() => null);
  if (res.ok && json) return { kind: "ok", result: json as ResultEnvelope<M, S> };
  if (isApiError(json)) {
    // Field errors (validation_error, or e.g. no_such_data naming an input) show inline.
    if (json.error.code === "validation_error" || Object.keys(json.error.fields ?? {}).length > 0) {
      return { kind: "invalid", message: json.error.message, fields: json.error.fields };
    }
    if (json.error.code === "source_unavailable") return { kind: "failed", message: t.sourceUnavailable };
    return { kind: "failed", message: json.error.message };
  }
  return { kind: "failed", message: t.computeUnavailable };
}
