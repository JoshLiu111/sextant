import { getMessages } from "@/i18n";
import type { ResultEnvelope } from "@/lib/envelope";

/** Traceability line under a result: data source, calculation id and time. */
export function CalculationInfo({ result }: { result: ResultEnvelope }) {
  const t = getMessages().common.calculation;
  return (
    <p className="text-xs text-black/50 dark:text-white/50">
      {t.source}: {result.source.name} · {t.computedAt}: {new Date(result.meta.computed_at).toISOString()} ·{" "}
      <span data-testid="calculation-id" className="break-all font-mono">
        {t.id} {result.calculation_id}
      </span>
    </p>
  );
}
