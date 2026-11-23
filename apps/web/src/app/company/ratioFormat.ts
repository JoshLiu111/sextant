import { getMessages } from "@/i18n";
import { formatValue } from "@/lib/format";

const TWO = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const ONE = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const WHOLE = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** A ratio value in its unit; `id` is the metric id ("<ratio>:<TICKER>:<period>"). */
export function formatRatio(value: number, unit: string | null, id: string): string {
  const r = getMessages().companyRatios;
  if (unit === "signal") return value === 1 ? r.pass : r.fail;
  if (id.startsWith("piotroski_f:")) return `${WHOLE.format(value)} / 9`;
  if (unit === "days") return `${ONE.format(value)} ${r.days}`;
  if (unit === "currency") return `${WHOLE.format(value / 1e6)}${r.currencyMillions}`;
  if (unit === "per_share" || unit === "score" || unit === "ratio") return TWO.format(value);
  return formatValue(value, unit);
}
