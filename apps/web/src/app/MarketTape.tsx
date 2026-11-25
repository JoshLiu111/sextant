import { cacheLife } from "next/cache";
import { computeFetch } from "@/lib/compute";
import type { MetricResult, ResultEnvelope, SeriesResult } from "@/lib/envelope";
import { getMessages } from "@/i18n";
import { formatValue } from "@/lib/format";
import { TapeTrack, type TapeItem } from "./TapeTrack";

type Key = keyof ReturnType<typeof getMessages>["home"]["tape"]["items"];

// The Macro Dashboard's cards, in tape order: the endpoint each comes from,
// where it sits on /macro, and the series whose last two readings give its change.
const SOURCES: readonly { path: `/${string}`; href: string; keys: readonly { key: Key; history?: string }[] }[] = [
  {
    path: "/macro/indicators",
    href: "/macro#us",
    keys: [
      { key: "cpi_inflation", history: "history:cpi_inflation" },
      { key: "unemployment_rate", history: "history:unemployment_rate" },
      { key: "fed_funds_rate", history: "history:fed_funds_rate" },
      { key: "gdp_growth", history: "history:gdp_growth" },
    ],
  },
  {
    path: "/macro/rates",
    href: "/macro#macro-rates",
    keys: [{ key: "yield_2y" }, { key: "yield_10y" }, { key: "spread_10y_2y", history: "history:spread_10y_2y" }],
  },
  {
    path: "/macro/euro-area",
    href: "/macro#euro-area",
    keys: [
      { key: "hicp_inflation", history: "history:hicp_inflation" },
      { key: "deposit_facility_rate", history: "history:deposit_facility_rate" },
      { key: "main_refinancing_rate", history: "history:main_refinancing_rate" },
      { key: "marginal_lending_rate", history: "history:marginal_lending_rate" },
    ],
  },
];

/** The latest reading minus the one before it, from the series' last two non-empty points. */
function changeOf(series: SeriesResult | undefined): number | null {
  if (!series || series.status !== "ok") return null;
  const ys = series.points.map((p) => p.y).filter((y): y is number => typeof y === "number");
  if (ys.length < 2) return null;
  return Math.round((ys[ys.length - 1] - ys[ys.length - 2]) * 100) / 100;
}

async function fetchEnvelope(path: `/${string}`): Promise<ResultEnvelope<string, string> | null> {
  try {
    const res = await computeFetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(15000),
    });
    return res.ok ? ((await res.json()) as ResultEnvelope<string, string>) : null;
  } catch {
    return null;
  }
}

/**
 * Every reading the compute service returned, cached for hours. When any call
 * failed (always so at build time, when the service isn't reachable), the result
 * is cached for seconds: Next.js then leaves the tape out of the prerendered
 * landing page and fetches it per request, instead of shipping an empty tape.
 */
async function getTape(): Promise<TapeItem[]> {
  "use cache";
  const labels = getMessages().home.tape.items;
  const envelopes = await Promise.all(SOURCES.map((s) => fetchEnvelope(s.path)));
  const items: TapeItem[] = [];
  envelopes.forEach((envelope, i) => {
    if (!envelope) return;
    for (const { key, history } of SOURCES[i].keys) {
      const metric: MetricResult | undefined = envelope.metrics[`latest:${key}`];
      if (!metric || metric.status !== "ok" || typeof metric.value !== "number") continue;
      items.push({
        key,
        label: labels[key],
        value: formatValue(metric.value, metric.unit),
        change: history ? changeOf(envelope.series[history]) : null,
        href: SOURCES[i].href,
      });
    }
  });
  if (envelopes.every(Boolean)) cacheLife("hours");
  else cacheLife("seconds");
  return items;
}

/** The band of live readings under the nav. Renders nothing when the service is down. */
export async function MarketTape() {
  const items = await getTape();
  if (items.length === 0) return null;
  return <TapeTrack items={items} />;
}

/** The tape's empty band, holding its place while the readings stream in. */
export function TapeFallback() {
  return <div aria-hidden className="tape tape-placeholder" />;
}
