import "server-only";

import { computeFetchAsUser } from "@/lib/auth/session";

// Operator view of AI usage and users (compute: /api/compute/operator/...). Only accounts in
// the compute service's OPERATOR_EMAILS get in; for everyone else both endpoints
// answer 404, and so does /operator (see src/proxy.ts).

export type UsageTotals = {
  calls: number;
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

export type OperatorResult<T> = { kind: "ok"; report: T } | { kind: "not_found" } | { kind: "failed" };

async function fetchReport<T>(token: string | null, path: `/${string}`): Promise<OperatorResult<T>> {
  if (!token) return { kind: "not_found" };
  try {
    const res = await computeFetchAsUser(token, path, { signal: AbortSignal.timeout(10000) });
    if (res.status === 404) return { kind: "not_found" };
    if (!res.ok) return { kind: "failed" };
    return { kind: "ok", report: (await res.json()) as T };
  } catch {
    return { kind: "failed" };
  }
}

export type AiUsageResult = OperatorResult<AiUsageReport>;

export function fetchAiUsage(token: string | null): Promise<AiUsageResult> {
  return fetchReport(token, "/operator/ai-usage");
}

export type UsersReport = {
  since: string;
  until: string;
  total_users: number;
  /** Every UTC day in the window, newest first, including days without sign-ups. */
  sign_ups: { day: string; users: number }[];
  /** Users whose last sign-in falls within N days (7 and 30). Undercounts daily use. */
  signed_in_within: { days: number; users: number }[];
};

export function fetchUsers(token: string | null): Promise<OperatorResult<UsersReport>> {
  return fetchReport(token, "/operator/users");
}
