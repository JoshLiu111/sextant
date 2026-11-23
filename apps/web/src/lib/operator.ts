import "server-only";

import { computeFetchAsUser } from "@/lib/auth/session";

// Operator view of AI usage (compute: /api/compute/operator/...). Only accounts in
// the compute service's OPERATOR_EMAILS get in; for everyone else both endpoints
// answer 404, and so does /operator (see src/proxy.ts).

export type UsageTotals = {
  /** Every call, failed ones included. */
  calls: number;
  /** Calls the model failed on: not charged to the user's quota, but their tokens count. */
  failed_calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
};

export type UserUsage = UsageTotals & { user_id: string; email: string; name: string | null };

export type DayUsage = UserUsage & { day: string };

export type AiUsageReport = {
  since: string;
  until: string;
  pricing: { input_usd_per_mtok: number; output_usd_per_mtok: number };
  totals: UsageTotals;
  users: UserUsage[];
  days: DayUsage[];
};

/** True when `token` belongs to an operator. Any failure counts as "no". */
export async function isOperator(token: string | null): Promise<boolean> {
  if (!token) return false;
  try {
    const res = await computeFetchAsUser(token, "/operator/access", { signal: AbortSignal.timeout(5000) });
    return res.status === 204;
  } catch {
    return false;
  }
}

export type AiUsageResult = { kind: "ok"; report: AiUsageReport } | { kind: "not_found" } | { kind: "failed" };

export async function fetchAiUsage(token: string | null): Promise<AiUsageResult> {
  if (!token) return { kind: "not_found" };
  try {
    const res = await computeFetchAsUser(token, "/operator/ai-usage", { signal: AbortSignal.timeout(10000) });
    if (res.status === 404) return { kind: "not_found" };
    if (!res.ok) return { kind: "failed" };
    return { kind: "ok", report: (await res.json()) as AiUsageReport };
  } catch {
    return { kind: "failed" };
  }
}
