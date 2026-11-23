import { getMessages } from "@/i18n";
import type { AnswerCitation, AnswerSegment } from "@/lib/answer";
import type { Unit } from "@/lib/envelope";
import { formatValue } from "@/lib/format";

/** Where a citation links to: the cited calculation's raw result, when the page shows it. */
export type CitationLink = (calculationId: string) => { href: string; onClick: () => void };

/**
 * An AI answer (AI Analyst or AI Explain) in paragraphs, with every number shown
 * as what it is: a citation that matches its calculation (underlined), one that
 * doesn't (red, with a notice under the answer), or a number that cites nothing
 * and so was not checked (grey). Render it inside the answer's container:
 * `<CheckedAnswer segments={answer.answer} />`.
 */
export function CheckedAnswer({ segments, link }: { segments: AnswerSegment[]; link?: CitationLink }) {
  const t = getMessages().answer;
  const mismatches = segments.filter((s) => s.type === "citation" && !s.matches).length;
  const uncited = segments.some((s) => s.type === "uncited");
  return (
    <>
      {paragraphs(segments).map((paragraph, i) => (
        <p key={i}>
          {paragraph.map((segment, j) =>
            segment.type === "text" ? (
              <span key={j}>{segment.text}</span>
            ) : segment.type === "uncited" ? (
              <span
                key={j}
                data-testid="uncited-number"
                title={t.uncited}
                className="rounded bg-black/5 px-0.5 dark:bg-white/10"
              >
                {segment.text}
              </span>
            ) : (
              <Cited key={j} citation={segment} link={link} />
            ),
          )}
        </p>
      ))}
      {mismatches > 0 && (
        <p
          data-testid="mismatch-notice"
          role="alert"
          className="rounded-md bg-red-50 p-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-100"
        >
          {t.mismatchNotice(mismatches)}
        </p>
      )}
      {uncited && (
        <p data-testid="uncited-notice" className="text-xs text-black/60 dark:text-white/60">
          {t.uncitedNotice}
        </p>
      )}
    </>
  );
}

/** Split the answer into paragraphs at blank lines, keeping numbers in place. */
function paragraphs(segments: AnswerSegment[]): AnswerSegment[][] {
  const out: AnswerSegment[][] = [[]];
  for (const segment of segments) {
    if (segment.type !== "text") {
      out[out.length - 1].push(segment);
      continue;
    }
    segment.text.split(/\n\s*\n/).forEach((part, i) => {
      if (i > 0) out.push([]);
      if (part) out[out.length - 1].push({ type: "text", text: part });
    });
  }
  return out.filter((p) => p.some((s) => s.type !== "text" || s.text.trim()));
}

function Cited({ citation, link }: { citation: AnswerCitation; link?: CitationLink }) {
  const t = getMessages().answer;
  // The title is the citation's accessible description (its name is the number).
  const description = citation.matches
    ? link
      ? `${t.citationOk(citation.calculation_id)} ${t.openRawResult}`
      : t.citationOk(citation.calculation_id)
    : citation.actual !== null
      ? t.citationMismatch(formatValue(citation.actual, citation.unit as Unit | null), citation.calculation_id)
      : t.citationMissing(citation.reason ?? "");
  const className = citation.matches
    ? "font-medium underline decoration-dotted underline-offset-2"
    : "rounded bg-red-50 px-0.5 font-semibold text-red-700 underline decoration-wavy underline-offset-2 dark:bg-red-950 dark:text-red-300";
  const props = { "data-testid": "citation", "data-matches": String(citation.matches), title: description, className };
  if (!link) return <span {...props}>{citation.text}</span>;
  return (
    <a {...props} {...link(citation.calculation_id)}>
      {citation.text}
    </a>
  );
}
