"use client";

import { useState, type FormEvent } from "react";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice } from "@/components/ErrorNotice";
import { TextField } from "@/components/TextField";
import { getMessages } from "@/i18n";
import type { ResultEnvelope } from "@/lib/envelope";
import { useCompute } from "@/lib/useCompute";

// Mirrors EarningsEnvelope in apps/compute/sextant_compute/screener/calendar.py.
type EarningsEvent = {
  ticker: string;
  company: string;
  cik: number;
  date: string;
  status: "reported" | "expected";
  form: string;
  accession: string;
  url: string;
  based_on: string | null;
};
type EarningsResult = ResultEnvelope & { start: string; end: string; as_of: string; tickers: string[]; events: EarningsEvent[] };
type Query = { tickers?: string; start?: string; end?: string };

// Must match CALENDAR_TICKERS in the compute service (the default list).
const DEFAULT_TICKERS = "AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, JPM, V, WMT, PG, JNJ, KO, XOM, NFLX";

export function EarningsCalendar() {
  const t = getMessages();
  const m = t.screener.earnings;
  const [tickers, setTickers] = useState(DEFAULT_TICKERS);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [query, setQuery] = useState<Query>({});
  const { result, fieldErrors, error, pending, run } = useCompute("/screener/earnings", query);
  const calendar = result as EarningsResult | null;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const next: Query = {};
    if (tickers.trim() && tickers.trim() !== DEFAULT_TICKERS) next.tickers = tickers;
    if (start) next.start = start;
    if (end) next.end = end;
    if (JSON.stringify(next) === JSON.stringify(query)) run();
    else setQuery(next);
  }

  return (
    <section aria-labelledby="earnings-section" className="mt-12 space-y-4">
      <h2 id="earnings-section" className="text-xl font-semibold">
        {m.heading}
      </h2>
      <p className="text-sm text-black/70 dark:text-white/70">{m.intro}</p>
      <form onSubmit={onSubmit} noValidate className="flex flex-wrap items-start gap-4">
        <div className="w-full max-w-xl">
          <TextField name="tickers" label={m.tickers.label} hint={m.tickers.hint} value={tickers} onChange={setTickers} error={fieldErrors.tickers} />
        </div>
        <div className="w-44">
          <TextField name="start" type="date" label={m.start.label} hint={m.start.hint} value={start} onChange={setStart} error={fieldErrors.start} />
        </div>
        <div className="w-44">
          <TextField name="end" type="date" label={m.end.label} hint={m.end.hint} value={end} onChange={setEnd} error={fieldErrors.end} />
        </div>
        <button
          type="submit"
          className="mt-6 rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
        >
          {m.submit}
        </button>
      </form>

      <div aria-busy={pending} className="min-w-0 space-y-3">
        {error && (
          <ErrorNotice
            title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
            message={error}
          />
        )}
        {calendar ? (
          <>
            <h3 data-testid="earnings-range" className="text-base font-semibold">
              {m.range(calendar.start, calendar.end)}
            </h3>
            {calendar.events.length === 0 ? (
              <p className="text-sm text-black/60 dark:text-white/60">{m.none}</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
                <table aria-label={m.tableLabel} className="w-full min-w-[36rem] border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-black/10 text-left dark:border-white/10">
                      <th scope="col" className="px-2 py-2 font-medium">
                        {m.date}
                      </th>
                      <th scope="col" className="px-2 py-2 font-medium">
                        {m.company}
                      </th>
                      <th scope="col" className="px-2 py-2 font-medium">
                        {m.status}
                      </th>
                      <th scope="col" className="px-2 py-2 font-medium">
                        {m.filing}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {calendar.events.map((e) => (
                      <tr
                        key={`${e.ticker}-${e.status}-${e.date}-${e.accession}`}
                        data-ticker={e.ticker}
                        data-status={e.status}
                        className="border-b border-black/5 last:border-0 dark:border-white/5"
                      >
                        <td className="whitespace-nowrap px-2 py-1.5 font-mono text-xs">{e.date}</td>
                        <td className="px-2 py-1.5">
                          <span className="font-mono text-xs">{e.ticker}</span> {e.company}
                        </td>
                        <td className={`px-2 py-1.5 ${e.status === "expected" ? "italic text-black/60 dark:text-white/60" : ""}`}>
                          {e.status === "reported" ? m.reported : m.expected}
                        </td>
                        <td className="px-2 py-1.5">
                          <a href={e.url} target="_blank" rel="noreferrer" className="underline decoration-dotted">
                            {e.status === "reported" ? m.reportedLink(e.form, e.date) : m.expectedLink(e.form, e.based_on ?? "")}
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <CalculationInfo result={calendar} />
          </>
        ) : (
          !error && <p className="text-sm text-black/60 dark:text-white/60">{m.loading}</p>
        )}
      </div>
    </section>
  );
}
