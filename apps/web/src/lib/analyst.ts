// Browser client for AI Analyst (`POST /api/compute/ai/analyst`). Mirrors
// apps/compute/sextant_compute/ai/analyst.py. The session cookie authenticates the call.

import { getMessages } from "@/i18n";
import type { AiQuota } from "./ai";
import type { AnswerSegment } from "./answer";
import { computePath } from "./compute";
import type { ApiErrorBody, ResultEnvelope } from "./envelope";

export type AnalystToolCall = {
  id: string;
  tool: string;
  input: unknown;
  calculation_id: string | null;
  error: string | null;
};

export type AnalystAnswer = {
  question: string;
  answer: AnswerSegment[];
  calls: AnalystToolCall[];
  calculations: Record<string, ResultEnvelope>;
  advice_notice: string | null;
  usage: { input_tokens: number; output_tokens: number };
  quota: AiQuota;
};

export type AskOutcome =
  | { kind: "ok"; answer: AnalystAnswer }
  | { kind: "invalid"; message: string }
  | { kind: "quota_exceeded"; message: string }
  | { kind: "signed_out" }
  | { kind: "failed"; message: string };

export async function askAnalyst(question: string): Promise<AskOutcome> {
  const fallback = getMessages().analyst.unavailable;
  let res: Response;
  try {
    res = await fetch(computePath("/ai/analyst"), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    return { kind: "failed", message: fallback };
  }
  if (res.status === 401) return { kind: "signed_out" };
  const json: unknown = await res.json().catch(() => null);
  if (res.ok && json) return { kind: "ok", answer: json as AnalystAnswer };
  const error = (json as ApiErrorBody | null)?.error;
  if (error?.code === "quota_exceeded")
    return { kind: "quota_exceeded", message: error.message };
  if (error?.code === "validation_error") {
    return { kind: "invalid", message: error.fields.question ?? error.message };
  }
  return { kind: "failed", message: error?.message ?? fallback };
}
