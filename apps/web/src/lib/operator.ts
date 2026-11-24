import "server-only";

import { answersAsUser, computeFetchAsUser } from "@/lib/auth/session";

// Operator view of AI usage and users (compute: /api/compute/operator/...). Only accounts in
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
export function isOperator(token: string | null): Promise<boolean> {
  return answersAsUser(token, "/operator/access", (res) => res.status === 204);
}

export type OperatorResult<T> = { kind: "ok"; report: T } | { kind: "not_found" } | { kind: "failed" };

/** The windows the operator can pick, in UTC days (today included). */
export const WINDOW_DAYS = [7, 30, 90] as const;
export type WindowDays = (typeof WINDOW_DAYS)[number];
export const DEFAULT_WINDOW_DAYS: WindowDays = 30;

/** The window a `?days=` search param asks for; anything else is the default. */
export function windowDays(param: string | string[] | undefined): WindowDays {
  const days = Number(param);
  return WINDOW_DAYS.find((d) => d === days) ?? DEFAULT_WINDOW_DAYS;
}

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

export function fetchAiUsage(token: string | null, days: WindowDays): Promise<OperatorResult<AiUsageReport>> {
  return fetchReport(token, `/operator/ai-usage?days=${days}`);
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

export function fetchUsers(token: string | null, days: WindowDays): Promise<OperatorResult<UsersReport>> {
  return fetchReport(token, `/operator/users?days=${days}`);
}
