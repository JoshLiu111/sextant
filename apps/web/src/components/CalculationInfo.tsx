import { getMessages } from "@/i18n";
import type { ResultEnvelope } from "@/lib/envelope";
import { formatTimestampEt } from "@/lib/format";

/** Traceability line under a result: data source, calculation id and time. */
export function CalculationInfo({ result }: { result: ResultEnvelope }) {
  const t = getMessages().common.calculation;
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      <span>
        {t.source}: {result.source.name}
      </span>
      <span>
        {t.computedAt}:{" "}
        <time dateTime={result.meta.computed_at} className="tabular-nums">
          {formatTimestampEt(result.meta.computed_at)}
        </time>
      </span>
      <span data-testid="calculation-id" className="break-all tabular-nums">
        {t.id} {result.calculation_id}
      </span>
    </p>
  );
}
