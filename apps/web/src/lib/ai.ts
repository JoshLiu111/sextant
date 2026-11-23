// Browser client for AI Explain (`/api/compute/ai/...`). Mirrors
// apps/compute/sextant_compute/ai/api.py. The session cookie authenticates the call.

import { getMessages } from "@/i18n";
import { computePath } from "./compute";
import type { ApiErrorBody } from "./envelope";

export type AiQuota = { limit: number; used: number; remaining: number; resets_at: string };

export type AiExplanation = {
  tool: string;
  calculation_id: string;
  explanation: string;
  /** Set when the answer touches on buying or selling. */
  advice_notice: string | null;
  usage: { input_tokens: number; output_tokens: number };
  quota: AiQuota;
};

export type QuotaOutcome = { kind: "ok"; quota: AiQuota } | { kind: "signed_out" } | { kind: "failed" };

export type ExplainOutcome =
  | { kind: "ok"; explanation: AiExplanation }
  | { kind: "quota_exceeded"; message: string }
  | { kind: "signed_out" }
  | { kind: "failed"; message: string };

export async function fetchAiQuota(signal?: AbortSignal): Promise<QuotaOutcome> {
  try {
    const res = await fetch(computePath("/ai/quota"), { signal });
    if (res.status === 401) return { kind: "signed_out" };
    if (!res.ok) return { kind: "failed" };
    return { kind: "ok", quota: (await res.json()) as AiQuota };
  } catch (err) {
    if (signal?.aborted) throw err;
    return { kind: "failed" };
  }
}

/** Ask for an explanation of the result computed from `parameters` (the envelope's `meta.parameters`). */
export async function explainResult(tool: string, parameters: Record<string, unknown>): Promise<ExplainOutcome> {
  const fallback = getMessages().ai.unavailable;
  let res: Response;
  try {
    res = await fetch(computePath(`/ai/explain/${encodeURIComponent(tool)}`), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(parameters),
    });
  } catch {
    return { kind: "failed", message: fallback };
  }
  if (res.status === 401) return { kind: "signed_out" };
  const json: unknown = await res.json().catch(() => null);
  if (res.ok && json) return { kind: "ok", explanation: json as AiExplanation };
  const error = (json as ApiErrorBody | null)?.error;
  if (error?.code === "quota_exceeded") return { kind: "quota_exceeded", message: error.message };
  return { kind: "failed", message: error?.message ?? fallback };
}
