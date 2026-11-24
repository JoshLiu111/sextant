"use client";

import { useEffect, useRef } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { getMessages } from "@/i18n";
import type { ResultEnvelope, Unit } from "@/lib/envelope";
import { formatStatementValue } from "@/lib/format";
import { useCompute } from "@/lib/useCompute";
import type { Frequency } from "./FrequencyToggle";
import { formatRatio } from "./ratioFormat";

// Mirrors InputsEnvelope in apps/compute/sextant_compute/company/ratios.py.
type Source = {
  period_id: string;
  period_label: string;
  value: number | null;
  reason: string | null;
  form: string | null;
  filed: string | null;
  url: string | null;
  derived_from: string | null;
};
type Input = {
  item: string;
  label: string;
  unit: Unit;
  period_id: string;
  period_label: string;
  value: number | null;
  reason: string | null;
  basis: "reported" | "ttm";
  sources: Source[];
};
type InputsResult = ResultEnvelope & { inputs: Input[] };

export type Selection = {
  ratio: string;
  ticker: string;
  period: string;
  periodLabel: string;
  price: number | null;
  frequency: Frequency;
};

function SourceLine({ source, unit, showPeriod }: { source: Source; unit: Unit; showPeriod: boolean }) {
  const d = getMessages().companyRatios.drill;
  return (
    <li>
      {showPeriod && (
        <span>
          {source.period_label}:{" "}
          <span className="tabular-nums">
            {source.value === null ? "n/a" : formatStatementValue(source.value, unit)}
          </span>{" "}
          ·{" "}
        </span>
      )}
      {source.url ? (
        <a href={source.url} target="_blank" rel="noreferrer" className="link whitespace-nowrap">
          {source.form} {d.filed} {source.filed}
        </a>
      ) : (
        <span className="italic">{source.reason}</span>
      )}
      {source.derived_from && (
        <span className="block text-xs text-muted">
          {d.derived}: {source.derived_from}
        </span>
      )}
    </li>
  );
}

/** The drill-down behind one ratio value: formula, value, and each input with its filings. */
export function RatioInputs({ selection, onClose }: { selection: Selection; onClose: () => void }) {
  const r = getMessages().companyRatios;
  const d = r.drill;
  const ref = useRef<HTMLDialogElement>(null);
  const { result, error } = useCompute("/company/ratios/inputs", {
    ticker: selection.ticker,
    ratio: selection.ratio,
    period: selection.period,
    frequency: selection.frequency,
    price: selection.price,
  });
  const inputs = result as InputsResult | null;
  const metricId = `${selection.ratio}:${selection.ticker}:${selection.period}`;
  const metric = inputs?.metrics[metricId];
  const explainer = r.ratios[selection.ratio];

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby="ratio-inputs-title"
      onClose={onClose}
      className="w-[min(48rem,calc(100vw-2rem))] rounded-card border border-rule bg-paper p-0 text-ink shadow-sheet backdrop:bg-ink/40"
    >
      <div className="space-y-4 p-5">
        <div className="flex items-start justify-between gap-4">
          <h2 id="ratio-inputs-title" className="text-xl">
            {d.title(explainer.name, selection.ticker, selection.periodLabel)}
          </h2>
          <button
            type="button"
            onClick={() => ref.current?.close()}
            className="btn btn-sm shrink-0 whitespace-nowrap"
          >
            {d.close}
          </button>
        </div>
        <dl className="max-w-[75ch] space-y-2 text-sm">
          <div>
            <dt className="text-muted">{d.formula}</dt>
            <dd>{explainer.how}</dd>
          </div>
          <div>
            <dt className="text-muted">{d.value}</dt>
            <dd>
              {!metric ? (
                "…"
              ) : metric.status === "ok" && metric.value !== null ? (
                <span className="tabular-nums">{formatRatio(metric.value, metric.unit, metricId)}</span>
              ) : (
                <span className="italic">{metric.reason}</span>
              )}
            </dd>
          </div>
        </dl>
        {error && <ErrorNotice title={getMessages().common.errors.heading} message={error} />}
        {inputs ? (
          inputs.inputs.length === 0 ? (
            <p className="text-sm">{d.noInputs}</p>
          ) : (
            <section aria-labelledby="ratio-inputs-table">
              <h3 id="ratio-inputs-table" className="text-lg">
                {d.inputs}
              </h3>
              <p className="text-xs text-muted">{d.unitsNote}</p>
              <div className="relative mt-2 max-h-[50vh] overflow-auto">
                <table aria-labelledby="ratio-inputs-table" className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-ink text-left text-xs text-muted">
                      <th scope="col" className="sticky left-0 top-0 z-20 whitespace-nowrap bg-paper py-2 pr-3 font-medium">
                        {d.input}
                      </th>
                      <th scope="col" className="sticky top-0 z-10 whitespace-nowrap bg-paper px-3 py-2 font-medium">
                        {d.period}
                      </th>
                      <th scope="col" className="sticky top-0 z-10 whitespace-nowrap bg-paper px-3 py-2 text-right font-medium">
                        {d.amount}
                      </th>
                      <th scope="col" className="sticky top-0 z-10 whitespace-nowrap bg-paper px-3 py-2 font-medium">
                        {d.source}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {inputs.inputs.map((i) => (
                      <tr
                        key={`${i.item}:${i.period_id}`}
                        className="border-b border-rule align-top last:border-0"
                      >
                        <th scope="row" className="sticky left-0 z-10 bg-paper py-1.5 pr-3 text-left font-normal">
                          {i.label}
                        </th>
                        <td className="whitespace-nowrap px-3 py-1.5">
                          {i.period_label}
                          {i.basis === "ttm" && (
                            <span title={d.ttm} className="ml-1 text-xs text-muted">
                              ({r.ttm})
                            </span>
                          )}
                        </td>
                        <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">
                          {i.value === null ? <span className="font-sans italic">{i.reason}</span> : formatStatementValue(i.value, i.unit)}
                        </td>
                        <td className="px-3 py-1.5">
                          {i.basis === "ttm" && <p className="text-xs text-muted">{d.ttm}</p>}
                          <ul className="space-y-1">
                            {i.sources.map((s) => (
                              <SourceLine key={s.period_id} source={s} unit={i.unit} showPeriod={i.basis === "ttm"} />
                            ))}
                          </ul>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )
        ) : (
          !error && <p className="text-sm text-muted">{d.loading}</p>
        )}
      </div>
    </dialog>
  );
}
