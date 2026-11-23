"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { SignInLink } from "@/components/SignInLink";
import { getMessages } from "@/i18n";
import { fetchAiQuota, type AiQuota } from "@/lib/ai";
import {
  askAnalyst,
  type AnalystAnswer,
  type AnswerCitation,
  type AnswerSegment,
} from "@/lib/analyst";
import type { Unit } from "@/lib/envelope";
import { formatLocalTime, formatValue } from "@/lib/format";

type Account =
  | { kind: "loading" }
  | { kind: "signed_out" }
  | { kind: "signed_in"; quota: AiQuota | null };

/** Element id of a calculation's raw-result panel (citations link to it). */
function rawResultId(calculationId: string) {
  return `raw-${calculationId}`;
}

/** Open a calculation's raw result and scroll to it. */
function openRawResult(calculationId: string) {
  const panel = document.getElementById(rawResultId(calculationId));
  if (panel instanceof HTMLDetailsElement) {
    panel.open = true;
    panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

/**
 * AI Analyst: a signed-in user asks a question; Claude picks Sextant's tools,
 * Sextant runs them, and the answer cites each number's calculation. Cited
 * numbers that don't match their calculation are shown in red.
 */
export function AiAnalyst() {
  const t = getMessages().analyst;
  const ai = getMessages().ai;
  const [account, setAccount] = useState<Account>({ kind: "loading" });
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AnalystAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchAiQuota(controller.signal)
      .then((outcome) => {
        if (outcome.kind === "signed_out") setAccount({ kind: "signed_out" });
        else
          setAccount({
            kind: "signed_in",
            quota: outcome.kind === "ok" ? outcome.quota : null,
          });
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);

  const quota = account.kind === "signed_in" ? account.quota : null;
  const usedUp = quota !== null && quota.remaining <= 0;

  async function onAsk(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    const outcome = await askAnalyst(question);
    setPending(false);
    if (outcome.kind === "ok") {
      setAnswer(outcome.answer);
      setAccount({ kind: "signed_in", quota: outcome.answer.quota });
    } else if (outcome.kind === "quota_exceeded") {
      setAccount((a) => ({
        kind: "signed_in",
        quota:
          a.kind === "signed_in" && a.quota
            ? { ...a.quota, remaining: 0 }
            : null,
      }));
      setError(outcome.message);
    } else if (outcome.kind === "signed_out") {
      setAccount({ kind: "signed_out" });
    } else {
      setError(outcome.message);
    }
  }

  if (account.kind === "loading") return null;

  if (account.kind === "signed_out") {
    return (
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-black/10 p-4 text-sm dark:border-white/15">
        <p className="min-w-0 flex-1 text-black/70 dark:text-white/70">
          {t.signInPrompt}
        </p>
        <SignInLink className="rounded-md bg-black px-3 py-1.5 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black" />
      </div>
    );
  }

  return (
    <div className="mt-6 space-y-6">
      <form onSubmit={onAsk} className="space-y-3">
        <label htmlFor="analyst-question" className="block text-sm font-medium">
          {t.questionLabel}
        </label>
        <textarea
          id="analyst-question"
          name="question"
          rows={3}
          value={question}
          placeholder={t.questionPlaceholder}
          onChange={(e) => setQuestion(e.target.value)}
          className="w-full rounded-md border border-black/20 bg-transparent px-3 py-2 dark:border-white/25"
        />
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={pending || usedUp || question.trim() === ""}
            className="rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-white/80"
          >
            {pending ? t.pending : t.ask}
          </button>
          {quota && (
            <p
              data-testid="ai-quota"
              aria-live="polite"
              className="text-sm text-black/60 dark:text-white/60"
            >
              {ai.quota(quota.remaining, quota.limit)}
            </p>
          )}
        </div>
        {usedUp && (
          <p
            data-testid="ai-quota-used-up"
            className="text-sm text-black/70 dark:text-white/70"
          >
            {ai.usedUp(formatLocalTime(quota.resets_at))}
          </p>
        )}
      </form>

      {error && !usedUp && (
        <ErrorNotice title={t.errorHeading} message={error} />
      )}
      {answer && <Answer answer={answer} />}
    </div>
  );
}

function Answer({ answer }: { answer: AnalystAnswer }) {
  const t = getMessages().analyst;
  const headingId = useId();
  const mismatches = answer.answer.filter(
    (s) => s.type === "citation" && !s.matches,
  ).length;
  return (
    <section
      aria-labelledby={headingId}
      className="space-y-4 rounded-lg border border-black/10 p-4 dark:border-white/15"
    >
      <h2 id={headingId} className="text-lg font-semibold">
        {t.answerHeading}
      </h2>
      <div
        data-testid="analyst-answer"
        aria-live="polite"
        className="space-y-2 leading-relaxed"
      >
        {paragraphs(answer.answer).map((paragraph, i) => (
          <p key={i}>
            {paragraph.map((segment, j) =>
              segment.type === "text" ? (
                <span key={j}>{segment.text}</span>
              ) : (
                <Cited key={j} citation={segment} />
              ),
            )}
          </p>
        ))}
      </div>
      {mismatches > 0 && (
        <p
          data-testid="analyst-mismatch-notice"
          role="alert"
          className="rounded-md bg-red-50 p-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-100"
        >
          {t.mismatchNotice(mismatches)}
        </p>
      )}
      {answer.advice_notice && (
        <p
          data-testid="ai-advice-notice"
          className="rounded-md bg-amber-50 p-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100"
        >
          {answer.advice_notice}
        </p>
      )}
      <Calls answer={answer} />
      <p className="text-xs text-black/50 dark:text-white/50">
        {t.usage(answer.usage.input_tokens, answer.usage.output_tokens)}
      </p>
    </section>
  );
}

/** Split the answer into paragraphs at blank lines, keeping citations in place. */
function paragraphs(segments: AnswerSegment[]): AnswerSegment[][] {
  const out: AnswerSegment[][] = [[]];
  for (const segment of segments) {
    if (segment.type === "citation") {
      out[out.length - 1].push(segment);
      continue;
    }
    segment.text.split(/\n\s*\n/).forEach((part, i) => {
      if (i > 0) out.push([]);
      if (part) out[out.length - 1].push({ type: "text", text: part });
    });
  }
  return out.filter((p) =>
    p.some((s) => s.type === "citation" || s.text.trim()),
  );
}

function Cited({ citation }: { citation: AnswerCitation }) {
  const t = getMessages().analyst;
  // The title is the link's accessible description (its name is the number).
  const description = citation.matches
    ? t.citationOk(citation.calculation_id)
    : citation.actual !== null
      ? t.citationMismatch(
          formatValue(citation.actual, citation.unit as Unit | null),
          citation.calculation_id,
        )
      : t.citationMissing(citation.reason ?? "");
  return (
    <a
      href={`#${rawResultId(citation.calculation_id)}`}
      onClick={() => openRawResult(citation.calculation_id)}
      data-testid="citation"
      data-matches={String(citation.matches)}
      title={description}
      className={
        citation.matches
          ? "font-medium underline decoration-dotted underline-offset-2"
          : "rounded bg-red-50 px-0.5 font-semibold text-red-700 underline decoration-wavy underline-offset-2 dark:bg-red-950 dark:text-red-300"
      }
    >
      {citation.text}
    </a>
  );
}

function Calls({ answer }: { answer: AnalystAnswer }) {
  const t = getMessages().analyst;
  return (
    <div>
      <h3 className="font-medium">{t.callsHeading}</h3>
      {answer.calls.length === 0 ? (
        <p className="mt-1 text-sm text-black/60 dark:text-white/60">
          {t.noCalls}
        </p>
      ) : (
        <ol className="mt-2 space-y-3">
          {answer.calls.map((call) => {
            const result = call.calculation_id
              ? answer.calculations[call.calculation_id]
              : undefined;
            return (
              <li
                key={call.id}
                data-testid="analyst-call"
                className="min-w-0 rounded-md border border-black/10 p-3 text-sm dark:border-white/15"
              >
                <p className="font-mono font-medium">{call.tool}</p>
                <p className="mt-2 text-xs text-black/60 dark:text-white/60">
                  {t.parameters}
                </p>
                <pre
                  data-testid="analyst-call-input"
                  className="mt-1 overflow-x-auto rounded bg-black/5 p-2 text-xs dark:bg-white/10"
                >
                  {JSON.stringify(call.input, null, 2)}
                </pre>
                {call.error && (
                  <p className="mt-2 text-red-700 dark:text-red-400">
                    {t.callFailed}: {call.error}
                  </p>
                )}
                {call.calculation_id && result && (
                  <details
                    id={rawResultId(call.calculation_id)}
                    className="mt-2"
                  >
                    <summary className="cursor-pointer text-xs">
                      {t.rawResult} ({t.calculation}{" "}
                      <span className="break-all font-mono">
                        {call.calculation_id}
                      </span>
                      )
                    </summary>
                    <pre
                      data-testid="analyst-raw-result"
                      className="mt-1 max-h-96 overflow-auto rounded bg-black/5 p-2 text-xs dark:bg-white/10"
                    >
                      {JSON.stringify(result, null, 2)}
                    </pre>
                  </details>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
