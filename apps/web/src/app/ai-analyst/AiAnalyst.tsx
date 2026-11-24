"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { SignInLink } from "@/components/SignInLink";
import { getMessages } from "@/i18n";
import { fetchAiQuota, type AiQuota } from "@/lib/ai";
import { CheckedAnswer, type CitationLink } from "@/components/CheckedAnswer";
import { useReportSources } from "@/components/PageSources";
import { askAnalyst, type AnalystAnswer } from "@/lib/analyst";
import { sourcesOf } from "@/lib/envelope";
import { formatLocalTime } from "@/lib/format";
import { fieldsCodec, hrefWithQuery, useUrlInputs } from "@/lib/urlInputs";

// Shareable links: `/ai-analyst?question=...` fills in the question. It is not
// asked on load: each answer spends one of the user's daily AI calls.
const URL_CODEC = fieldsCodec({ question: "" });

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

const linkToRawResult: CitationLink = (calculationId) => ({
  href: `#${rawResultId(calculationId)}`,
  onClick: () => openRawResult(calculationId),
});

/**
 * AI Analyst: a signed-in user asks a question; Claude picks Sextant's tools,
 * Sextant runs them, and the answer cites each number's calculation. Cited
 * numbers that don't match their calculation are shown in red.
 */
export function AiAnalyst() {
  const t = getMessages().analyst;
  const ai = getMessages().ai;
  const [account, setAccount] = useState<Account>({ kind: "loading" });
  const { initial, share } = useUrlInputs(URL_CODEC);
  const [question, setQuestion] = useState(initial.question);
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
    share({ question });
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
      <div
        id="analyst"
        data-testid="analyst-sign-in"
        className="card mt-8 flex flex-wrap items-center justify-between gap-x-6 gap-y-3 p-4 text-sm md:p-5"
      >
        <p className="min-w-0 max-w-[65ch] flex-1 basis-48 text-ink-2">
          {t.signInPrompt}
        </p>
        {/* Back to the same question after signing in. */}
        <SignInLink
          returnTo={hrefWithQuery("/ai-analyst", { question: question || undefined })}
          className="btn btn-primary" />
      </div>
    );
  }

  return (
    <div id="analyst" className="mt-8 space-y-10">
      <form onSubmit={onAsk} className="max-w-[75ch] space-y-3">
        <label htmlFor="analyst-question" className="label">
          {t.questionLabel}
        </label>
        <textarea
          id="analyst-question"
          name="question"
          rows={3}
          value={question}
          placeholder={t.questionPlaceholder}
          onChange={(e) => setQuestion(e.target.value)}
          className="field resize-y py-2 leading-relaxed"
        />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <button
            type="submit"
            disabled={pending || usedUp || question.trim() === ""}
            className="btn btn-primary"
          >
            {pending ? t.pending : t.ask}
          </button>
          {quota && (
            <p
              data-testid="ai-quota"
              aria-live="polite"
              className="text-sm tabular-nums text-muted"
            >
              {ai.quota(quota.remaining, quota.limit)}
            </p>
          )}
        </div>
        {usedUp && (
          <p
            data-testid="ai-quota-used-up"
            className="text-sm tabular-nums text-ink-2"
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
  // The tool results credit their data in the footer, like any result on a tool page.
  useReportSources(
    Object.values(answer.calculations).flatMap((result) =>
      sourcesOf(result).map((s) => s.id),
    ),
  );
  return (
    <section
      aria-labelledby={headingId}
      className="space-y-5 border-t border-ink pt-6"
    >
      <h2 id={headingId} className="text-xl">
        {t.answerHeading}
      </h2>
      <div
        data-testid="analyst-answer"
        aria-live="polite"
        className="max-w-[75ch] space-y-2 leading-relaxed"
      >
        <CheckedAnswer segments={answer.answer} link={linkToRawResult} />
      </div>
      {answer.advice_notice && (
        <p
          data-testid="ai-advice-notice"
          className="well max-w-[75ch] px-3 py-2 text-sm"
        >
          {answer.advice_notice}
        </p>
      )}
      <Calls answer={answer} />
      <p className="text-xs tabular-nums text-muted">
        {t.usage(answer.usage.input_tokens, answer.usage.output_tokens)}
      </p>
    </section>
  );
}

function Calls({ answer }: { answer: AnalystAnswer }) {
  const t = getMessages().analyst;
  return (
    <div>
      <h3 className="text-lg">{t.callsHeading}</h3>
      {answer.calls.length === 0 ? (
        <p className="mt-1 text-sm text-muted">
          {t.noCalls}
        </p>
      ) : (
        <ol className="mt-3 divide-y divide-rule border-y border-rule">
          {answer.calls.map((call) => {
            const result = call.calculation_id
              ? answer.calculations[call.calculation_id]
              : undefined;
            return (
              <li
                key={call.id}
                data-testid="analyst-call"
                className="min-w-0 py-4 text-sm"
              >
                <p className="font-medium">{call.tool}</p>
                <p className="mt-2 text-xs text-muted">
                  {t.parameters}
                </p>
                <pre
                  data-testid="analyst-call-input"
                  className="well mt-1 overflow-x-auto px-3 py-2 font-sans text-xs tabular-nums"
                >
                  {JSON.stringify(call.input, null, 2)}
                </pre>
                {call.error && (
                  <p className="mt-2 text-red-700">
                    {t.callFailed}: {call.error}
                  </p>
                )}
                {call.calculation_id && result && (
                  <details
                    id={rawResultId(call.calculation_id)}
                    className="mt-2"
                  >
                    <summary className="link cursor-pointer py-1 text-xs text-ink-2">
                      {t.rawResult} ({t.calculation}{" "}
                      <span className="break-all tabular-nums">
                        {call.calculation_id}
                      </span>
                      )
                    </summary>
                    <pre
                      data-testid="analyst-raw-result"
                      className="well mt-1 max-h-96 overflow-auto px-3 py-2 font-sans text-xs tabular-nums"
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
