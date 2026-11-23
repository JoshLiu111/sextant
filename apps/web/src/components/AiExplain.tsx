"use client";

import { useEffect, useState } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { SignInLink } from "@/components/SignInLink";
import { getMessages } from "@/i18n";
import { explainResult, fetchAiQuota, type AiExplanation, type AiQuota } from "@/lib/ai";
import type { ResultEnvelope } from "@/lib/envelope";

type Account = { kind: "loading" } | { kind: "signed_out" } | { kind: "signed_in"; quota: AiQuota | null };

/**
 * "AI Explain" for a tool's current result. Signed-in users get a plain-English
 * reading of the result on screen and see their daily quota; visitors get a
 * sign-in prompt. Render it under a result: `<AiExplain tool="options" result={result} />`.
 */
export function AiExplain({ tool, result }: { tool: string; result: ResultEnvelope }) {
  const t = getMessages().ai;
  const [account, setAccount] = useState<Account>({ kind: "loading" });
  // The explanation belongs to the result it was asked for; a new result hides it.
  const [answer, setAnswer] = useState<{ for: string; explanation: AiExplanation } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchAiQuota(controller.signal)
      .then((outcome) => {
        if (outcome.kind === "signed_out") setAccount({ kind: "signed_out" });
        else setAccount({ kind: "signed_in", quota: outcome.kind === "ok" ? outcome.quota : null });
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);

  const quota = account.kind === "signed_in" ? account.quota : null;
  const usedUp = quota !== null && quota.remaining <= 0;
  const shown = answer?.for === result.calculation_id ? answer.explanation : null;

  async function onExplain() {
    const calculationId = result.calculation_id;
    setPending(true);
    setError(null);
    const outcome = await explainResult(tool, result.meta.parameters);
    setPending(false);
    if (outcome.kind === "ok") {
      setAnswer({ for: calculationId, explanation: outcome.explanation });
      setAccount({ kind: "signed_in", quota: outcome.explanation.quota });
    } else if (outcome.kind === "quota_exceeded") {
      setAccount((a) => ({ kind: "signed_in", quota: a.kind === "signed_in" && a.quota ? { ...a.quota, remaining: 0 } : null }));
      setError(outcome.message);
    } else if (outcome.kind === "signed_out") {
      setAccount({ kind: "signed_out" });
    } else {
      setError(outcome.message);
    }
  }

  return (
    <section
      aria-labelledby={`ai-explain-${tool}`}
      className="rounded-lg border border-black/10 p-4 dark:border-white/15"
    >
      <h2 id={`ai-explain-${tool}`} className="text-lg font-semibold">
        {t.heading}
      </h2>
      <p className="mt-1 text-sm text-black/60 dark:text-white/60">{t.intro}</p>

      {account.kind === "signed_out" && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm">
          <p className="min-w-0 flex-1 text-black/70 dark:text-white/70">{t.signInPrompt}</p>
          <SignInLink className="rounded-md bg-black px-3 py-1.5 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black" />
        </div>
      )}

      {account.kind === "signed_in" && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onExplain}
              disabled={pending || usedUp}
              className="rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-white/80"
            >
              {pending ? t.pending : t.button}
            </button>
            {quota && (
              <p data-testid="ai-quota" aria-live="polite" className="text-sm text-black/60 dark:text-white/60">
                {t.quota(quota.remaining, quota.limit)}
              </p>
            )}
          </div>
          {usedUp && (
            <p data-testid="ai-quota-used-up" className="text-sm text-black/70 dark:text-white/70">
              {t.usedUp}
            </p>
          )}
          {error && !usedUp && <ErrorNotice title={t.errorHeading} message={error} />}
          {shown && (
            <div data-testid="ai-explanation" aria-live="polite" className="space-y-2 text-sm leading-relaxed">
              {shown.explanation
                .split(/\n\s*\n/)
                .filter((p) => p.trim())
                .map((paragraph, i) => (
                  <p key={i}>{paragraph}</p>
                ))}
              {shown.advice_notice && (
                <p
                  data-testid="ai-advice-notice"
                  className="rounded-md bg-amber-50 p-2 text-amber-900 dark:bg-amber-950 dark:text-amber-100"
                >
                  {shown.advice_notice}
                </p>
              )}
              <p className="text-xs text-black/50 dark:text-white/50">
                {t.generatedBy} <span className="break-all font-mono">{shown.calculation_id}</span>
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
