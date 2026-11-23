import { getMessages } from "@/i18n";
import type { CsvTable } from "@/lib/csv";
import type { MetricResult } from "@/lib/envelope";
import { formatValue } from "@/lib/format";
import type { PortfolioEnvelope } from "./PortfolioResults";

/** Per-position metrics, `<column>:<TICKER>`; the totals row reads `<column>:portfolio`. */
export const POSITION_COLUMNS = [
  "quantity",
  "cost_basis",
  "market_value",
  "weight",
  "unrealized_pnl",
  "realized_pnl",
] as const;
type Column = (typeof POSITION_COLUMNS)[number];

const QUANTITY = new Intl.NumberFormat("en-US", { maximumFractionDigits: 6 });

/** Tickers in the envelope's order: holdings first, then positions an import sold out. */
function positionTickers(result: PortfolioEnvelope): string[] {
  return Object.keys(result.metrics)
    .filter((id) => id.startsWith("quantity:"))
    .map((id) => id.slice("quantity:".length));
}

/** Sum of the positions' weights (100%), or null while any weight is missing. */
function weightTotal(result: PortfolioEnvelope, tickers: string[]): number | null {
  const weights = tickers.map((t) => result.metrics[`weight:${t}`]);
  return weights.every((w) => w?.status === "ok" && w.value !== null)
    ? weights.reduce((sum, w) => sum + (w?.value ?? 0), 0)
    : null;
}

/** The positions table as CSV: raw values, one row per ticker, then the totals row. */
export function positionsCsvTable(result: PortfolioEnvelope): CsvTable {
  const s = getMessages().portfolio.saved;
  const tickers = positionTickers(result);
  return {
    columns: [s.sections.columns.ticker, ...POSITION_COLUMNS.map((c) => s.sections.columns[c])],
    rows: [
      ...tickers.map((ticker) => [ticker, ...POSITION_COLUMNS.map((c) => result.metrics[`${c}:${ticker}`])]),
      [
        s.sections.total,
        ...POSITION_COLUMNS.map((c) =>
          c === "quantity" ? null : c === "weight" ? weightTotal(result, tickers) : result.metrics[`${c}:portfolio`],
        ),
      ],
    ],
  };
}

function Cell({ id, result }: { id: string; result: MetricResult | undefined }) {
  const t = getMessages().common;
  let text = "";
  if (result?.status === "ok" && result.value !== null) {
    text = result.unit === null ? QUANTITY.format(result.value) : formatValue(result.value, result.unit);
  }
  return (
    <td
      data-position-value={id}
      data-status={result?.status ?? "pending"}
      title={result && result.status !== "ok" ? `${t.status[result.status]}: ${result.reason ?? ""}` : undefined}
      className="px-2 py-1.5 text-right font-mono tabular-nums"
    >
      {text || (result && result.status !== "ok" ? "—" : "")}
    </td>
  );
}

/** Quantity, cost basis, market value, weight and P&L per position, with a totals row. */
export function PositionsTable({ result, currency }: { result: PortfolioEnvelope | null; currency: string }) {
  const s = getMessages().portfolio.saved;
  if (!result) return null;
  const tickers = positionTickers(result);
  // Weights have no portfolio metric: the total is the sum of the positions' weights (100%).
  const totalWeight = weightTotal(result, tickers);
  return (
    <div>
      <div className="min-w-0 overflow-x-auto">
        <table aria-label={s.sections.positions} className="w-full min-w-[40rem] border-collapse text-sm">
          <caption className="mb-1 text-left text-sm text-black/70 dark:text-white/70">
            {s.sections.positionsNote} {currency && `(${currency})`}
          </caption>
          <thead>
            <tr className="border-b border-black/10 align-bottom dark:border-white/10">
              <th scope="col" className="px-2 py-2 text-left font-medium">
                {s.sections.columns.ticker}
              </th>
              {POSITION_COLUMNS.map((c) => (
                <th key={c} scope="col" className="px-2 py-2 text-right font-medium">
                  {s.sections.columns[c]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tickers.map((ticker) => (
              <tr key={ticker} data-ticker={ticker} className="border-b border-black/5 dark:border-white/5">
                <th scope="row" className="px-2 py-1.5 text-left font-mono font-normal">
                  {ticker}
                </th>
                {POSITION_COLUMNS.map((c) => (
                  <Cell key={c} id={`${c}:${ticker}`} result={result.metrics[`${c}:${ticker}`]} />
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-black/10 font-medium dark:border-white/10">
              <th scope="row" className="px-2 py-1.5 text-left">
                {s.sections.total}
              </th>
              {POSITION_COLUMNS.map((c: Column) => {
                if (c === "quantity") return <td key={c} />;
                if (c === "weight")
                  return (
                    <td key={c} className="px-2 py-1.5 text-right font-mono tabular-nums">
                      {totalWeight === null ? "—" : formatValue(totalWeight, "decimal")}
                    </td>
                  );
                return <Cell key={c} id={`${c}:portfolio`} result={result.metrics[`${c}:portfolio`]} />;
              })}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
