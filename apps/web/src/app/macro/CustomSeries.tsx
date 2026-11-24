"use client";

import { useState, type FormEvent } from "react";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice } from "@/components/ErrorNotice";
import { LineChart } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { TextField } from "@/components/TextField";
import { getMessages } from "@/i18n";
import { postCompute, type MetricResult, type ResultEnvelope, type SeriesResult } from "@/lib/envelope";
import {
  formatChartDate,
  formatChartPercentValue,
  formatSeriesNumber,
  formatTimestampUtc,
  formatValue,
} from "@/lib/format";
import { useUrlInputs, writeUrlInputs, type UrlCodec } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";
import { useReportSources } from "@/components/PageSources";
import { SeriesMeta } from "./MacroDashboard";
import { REFERENCE, series } from "@/lib/chartColors";

// POST /macro/search -> `results`; POST /macro/series -> metric `latest:<ID>`
// (details as /macro/indicators), series `history:<ID>`.
type SeriesHit = {
  id: string;
  title: string;
  units: string;
  frequency: string;
  seasonal_adjustment: string;
  last_updated: string;
  observation_end: string;
};
type SearchEnvelope = ResultEnvelope & { query: string; results: SeriesHit[] };
type AddedMetricId = `latest:${string}`;
type AddedSeriesId = `history:${string}`;

/** Matches MAX_SERIES in apps/compute/sextant_compute/macro/custom.py. */
const MAX_SERIES = 8;
const COLORS = [series(0), series(1), series(2), series(3), series(4), series(5), series(6), REFERENCE];

// Shareable links: `/macro?series=PAYEMS,UNRATENSA` (display order). Ids go to
// the API as given; a bad one shows the API's error.
const URL_CODEC: UrlCodec<string[]> = {
  keys: ["series"],
  read: (params) =>
    (params.get("series") ?? "")
      .split(",")
      .map((id) => id.trim().toUpperCase())
      .filter((id, i, all) => id && all.indexOf(id) === i),
  write: (ids) => ({ series: ids.length ? ids.join(",") : null }),
};

type SearchState =
  | { kind: "idle" }
  | { kind: "pending" }
  | { kind: "done"; query: string; results: SeriesHit[]; sourceId: string }
  | { kind: "invalid"; message: string }
  | { kind: "failed"; message: string };

/** Search FRED and add series to the board. `start` is the board's submitted chart range. */
export function CustomSeries({ start }: { start: string | undefined }) {
  const t = getMessages();
  const c = t.macro.custom;
  const { initial } = useUrlInputs(URL_CODEC);
  const [ids, setIds] = useState<string[]>(initial);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<SearchState>({ kind: "idle" });
  // Search hits on screen credit their source (FRED) in the footer.
  useReportSources(search.kind === "done" && search.results.length > 0 ? [search.sourceId] : []);

  function update(next: string[]) {
    setIds(next);
    writeUrlInputs(URL_CODEC, next);
  }

  async function onSearch(e: FormEvent) {
    e.preventDefault();
    setSearch({ kind: "pending" });
    const outcome = await postCompute("/macro/search", { query });
    if (outcome.kind === "ok") {
      const body = outcome.result as SearchEnvelope;
      setSearch({ kind: "done", query: body.query, results: body.results, sourceId: body.source.id });
    } else if (outcome.kind === "invalid") {
      setSearch({ kind: "invalid", message: outcome.fields.query ?? outcome.message });
    } else setSearch({ kind: "failed", message: outcome.message });
  }

  const full = ids.length >= MAX_SERIES;

  return (
    <section data-testid="custom-series" aria-labelledby="macro-custom" className="mt-12 space-y-6">
      <h3 id="macro-custom" className="text-xl">
        {c.heading}
      </h3>
      <p className="max-w-[75ch] text-sm text-ink-2">{c.intro}</p>
      <form onSubmit={onSearch} noValidate role="search" className="flex flex-wrap items-start gap-4">
        <div className="w-full max-w-sm">
          <TextField
            name="query"
            label={c.search.label}
            hint={c.search.hint}
            value={query}
            onChange={setQuery}
            error={search.kind === "invalid" ? search.message : undefined}
          />
        </div>
        <button
          type="submit"
          disabled={search.kind === "pending"}
          className="btn mt-6"
        >
          {c.submit}
        </button>
      </form>
      {search.kind === "failed" && <ErrorNotice title={t.common.errors.heading} message={search.message} />}
      {search.kind === "done" &&
        (search.results.length === 0 ? (
          <p data-testid="search-empty" className="text-sm text-ink-2">
            {c.empty(search.query)}
          </p>
        ) : (
          <ul aria-label={c.results} className="divide-y divide-rule border-y border-rule">
            {search.results.map((hit) => {
              const added = ids.includes(hit.id);
              return (
                <li key={hit.id} data-series-hit={hit.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">
                      {hit.title} <span className="tabular-nums text-muted">{hit.id}</span>
                    </p>
                    <p className="tabular-nums text-muted">
                      {hit.units} · {hit.frequency} ({hit.seasonal_adjustment}) · {t.macro.meta.lastUpdated}{" "}
                      {formatTimestampUtc(hit.last_updated)}
                    </p>
                  </div>
                  <button
                    type="button"
                    aria-label={c.add(hit.id)}
                    disabled={added || full}
                    onClick={() => update([...ids, hit.id])}
                    className="btn btn-sm"
                  >
                    {added ? c.added : c.addText}
                  </button>
                </li>
              );
            })}
          </ul>
        ))}
      {full && <p className="text-sm text-ink-2">{c.full(MAX_SERIES)}</p>}
      {ids.length > 0 && <AddedSeries ids={ids} start={start} onRemove={(id) => update(ids.filter((i) => i !== id))} />}
    </section>
  );
}

function AddedSeries({
  ids,
  start,
  onRemove,
}: {
  ids: string[];
  start: string | undefined;
  onRemove: (id: string) => void;
}) {
  const t = getMessages();
  const added = useCompute<AddedMetricId, AddedSeriesId>("/macro/series", start ? { series: ids, start } : { series: ids });
  const error = added.fieldErrors.series ?? added.error;

  return (
    <>
      {error && <ErrorNotice title={t.common.errors.heading} message={error} />}
      <div className="grid gap-6 lg:grid-cols-2">
        {ids.map((id, i) => (
          <Added
            key={id}
            id={id}
            color={COLORS[i % COLORS.length]}
            latest={added.result?.metrics[`latest:${id}`]}
            history={added.result?.series[`history:${id}`]}
            onRemove={() => onRemove(id)}
          />
        ))}
      </div>
      {added.result && <CalculationInfo result={added.result} />}
    </>
  );
}

function Added({
  id,
  color,
  latest,
  history,
  onRemove,
}: {
  id: string;
  color: string;
  latest: MetricResult | undefined;
  history: SeriesResult | undefined;
  onRemove: () => void;
}) {
  const t = getMessages();
  const c = t.macro.custom;
  const ok = latest?.status === "ok";
  const title = ok ? String(latest.details.title ?? id) : id;
  const percent = latest?.unit === "percent";
  const explainer = {
    name: title,
    ...c.explainer(title, ok ? String(latest.details.source ?? "") : "FRED", ok ? String(latest.details.units ?? "") : ""),
  };
  const points =
    history?.status === "ok" ? history.points.map((p) => ({ x: Date.parse(String(p.x)), y: p.y })) : [];

  return (
    <article data-indicator={`fred:${id}`} className="min-w-0 space-y-3">
      <MetricCard
        id={id}
        explainer={explainer}
        values={[{ id: `latest:${id}`, result: latest }]}
        format={(value, unit) => (unit === "percent" ? formatValue(value, unit) : formatSeriesNumber(value))}
      />
      {ok && <SeriesMeta details={latest.details} />}
      {points.length > 0 && (
        <LineChart
          label={`${title} ${t.macro.chart.history}`}
          series={[{ id, label: title, points, color }]}
          xLabel={t.macro.chart.x}
          formatX={formatChartDate}
          formatY={percent ? formatChartPercentValue : formatSeriesNumber}
          height={220}
        />
      )}
      <button
        type="button"
        aria-label={c.remove(id)}
        onClick={onRemove}
        className="btn btn-sm"
      >
        {c.removeText}
      </button>
    </article>
  );
}
