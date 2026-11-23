"use client";

// The data sources the results on the current page came from, for the footer
// attribution. Every result on screen reports the sources it used (`sourcesOf`):
// `useCompute` results and AI Analyst's tool results. The footer reads the union.

import { createContext, useCallback, useContext, useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { attributionFor, type AttributionId } from "@/lib/attributions";

type Registry = {
  credited: ReadonlySet<AttributionId>;
  report: (reporter: string, ids: readonly AttributionId[]) => void;
};

const PageSourcesContext = createContext<Registry | null>(null);

export function PageSourcesProvider({ children }: { children: ReactNode }) {
  const [byReporter, setByReporter] = useState<ReadonlyMap<string, readonly AttributionId[]>>(new Map());
  // Stable, so reporting components don't re-run their effects on every report.
  const report = useCallback((reporter: string, ids: readonly AttributionId[]) => {
    setByReporter((all) => {
      if (ids.length === 0 && !all.has(reporter)) return all;
      const next = new Map(all);
      if (ids.length > 0) next.set(reporter, ids);
      else next.delete(reporter);
      return next;
    });
  }, []);
  const registry = useMemo<Registry>(
    () => ({ credited: new Set([...byReporter.values()].flat()), report }),
    [byReporter, report],
  );
  return <PageSourcesContext.Provider value={registry}>{children}</PageSourcesContext.Provider>;
}

/** The attributions the page's current results call for. */
export function useCreditedSources(): ReadonlySet<AttributionId> {
  return useContext(PageSourcesContext)?.credited ?? new Set();
}

/**
 * Credit the sources of a result shown on the page (by compute `DataSource.id`),
 * for as long as the calling component is mounted. Ids without an attribution
 * (e.g. "user_input") are ignored.
 */
export function useReportSources(sourceIds: readonly (string | null | undefined)[]): void {
  const report = useContext(PageSourcesContext)?.report;
  const reporter = useId();
  const ids = [...new Set(sourceIds.flatMap((id) => (id ? [attributionFor(id)] : [])))].filter(
    (id): id is AttributionId => id !== null,
  );
  const key = ids.join(",");
  useEffect(() => {
    if (!report) return;
    report(reporter, key ? (key.split(",") as AttributionId[]) : []);
    return () => report(reporter, []);
  }, [report, reporter, key]);
}
