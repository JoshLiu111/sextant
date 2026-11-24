"use client";

import Link from "next/link";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getMessages } from "@/i18n";
import { fetchAiQuota, type AiQuota } from "@/lib/ai";
import { formatLocalTime } from "@/lib/format";
import { portfoliosApi } from "@/lib/portfolios";
import { PROVIDER_NAMES, PROVIDERS, providerKeysApi, type Provider } from "@/lib/providerKeys";

// The dashboard's status strip and the counts on its tool cards. Each item is
// fetched from an existing compute endpoint in the browser (so the quota reset
// shows in the user's own time zone) and loads or fails on its own: a failure
// shows "unavailable" for that item and leaves the rest of the page alone.

type Item<T> = { kind: "loading" } | { kind: "ok"; value: T } | { kind: "unavailable" };

type DashboardData = {
  keys: Item<Provider[]>;
  quota: Item<AiQuota>;
  portfolios: Item<number>;
};

const LOADING: DashboardData = { keys: { kind: "loading" }, quota: { kind: "loading" }, portfolios: { kind: "loading" } };

const DashboardContext = createContext<DashboardData>(LOADING);

const ok = <T,>(value: T): Item<T> => ({ kind: "ok", value });
const UNAVAILABLE = { kind: "unavailable" } as const;

/** Loads the status items once and shares them with the strip and the tool cards. */
export function DashboardDataProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<DashboardData>(LOADING);

  useEffect(() => {
    const controller = new AbortController();
    // After unmount (the abort) answers are dropped, whatever they are.
    const set = (patch: Partial<DashboardData>) => {
      if (!controller.signal.aborted) setData((d) => ({ ...d, ...patch }));
    };
    providerKeysApi
      .list()
      .then((o) => {
        if (o.kind !== "ok") return set({ keys: UNAVAILABLE });
        const saved = new Set(o.value.map((k) => k.provider));
        set({ keys: ok(PROVIDERS.filter((p) => saved.has(p))) });
      })
      .catch(() => set({ keys: UNAVAILABLE }));
    fetchAiQuota(controller.signal)
      .then((o) => set({ quota: o.kind === "ok" ? ok(o.quota) : UNAVAILABLE }))
      .catch(() => set({ quota: UNAVAILABLE }));
    portfoliosApi
      .list()
      .then((o) => set({ portfolios: o.kind === "ok" ? ok(o.value.length) : UNAVAILABLE }))
      .catch(() => set({ portfolios: UNAVAILABLE }));
    return () => controller.abort();
  }, []);

  return <DashboardContext.Provider value={data}>{children}</DashboardContext.Provider>;
}

const t = getMessages().dashboard;

const linkClass = "font-medium underline-offset-2 hover:underline";

function StatusItem<T>({
  id,
  heading,
  item,
  children,
}: {
  id: string;
  heading: string;
  item: Item<T>;
  children: (value: T) => ReactNode;
}) {
  return (
    <section
      aria-labelledby={`status-${id}`}
      aria-busy={item.kind === "loading"}
      className="rounded-lg border border-black/10 p-4 text-sm dark:border-white/15"
    >
      <h2 id={`status-${id}`} className="text-black/60 dark:text-white/60">
        {heading}
      </h2>
      <div className="mt-1 flex flex-col gap-1">
        {item.kind === "loading" && <p className="text-black/50 dark:text-white/50">{t.loading}</p>}
        {item.kind === "unavailable" && <p className="text-black/70 dark:text-white/70">{t.unavailable}</p>}
        {item.kind === "ok" && children(item.value)}
      </div>
    </section>
  );
}

export function StatusStrip() {
  const { keys, quota, portfolios } = useContext(DashboardContext);
  return (
    <div aria-label={t.statusLabel} role="group" className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <StatusItem id="key" heading={t.key.heading} item={keys}>
        {(providers) =>
          providers.length === 0 ? (
            <>
              <p className="text-base font-semibold">{t.key.none}</p>
              <Link href="/settings" className={linkClass}>
                {t.key.addKey}
              </Link>
            </>
          ) : (
            <>
              <p className="text-base font-semibold">{t.key.connected(providers.map((p) => PROVIDER_NAMES[p]))}</p>
              <Link href="/settings" className={linkClass}>
                {t.key.manage}
              </Link>
            </>
          )
        }
      </StatusItem>
      <StatusItem id="quota" heading={t.quota.heading} item={quota}>
        {(q) => (
          <>
            <p className="text-base font-semibold">{t.quota.left(q.remaining, q.limit)}</p>
            <p className="text-black/70 dark:text-white/70">{t.quota.resets(formatLocalTime(q.resets_at))}</p>
          </>
        )}
      </StatusItem>
      <StatusItem id="portfolios" heading={t.portfolios.heading} item={portfolios}>
        {(n) => (
          <>
            <p className="text-base font-semibold">{t.portfolios.count(n)}</p>
            <Link href="/portfolio" className={linkClass}>
              {t.portfolios.open}
            </Link>
          </>
        )}
      </StatusItem>
    </div>
  );
}

/** The saved-portfolio count, for the My Portfolio card's personal slot. */
export function SavedPortfolioCount() {
  const { portfolios } = useContext(DashboardContext);
  if (portfolios.kind === "loading") return null;
  return (
    <p data-testid="tool-card-personal" className="font-medium">
      {portfolios.kind === "ok" ? t.portfolios.count(portfolios.value) : t.unavailable}
    </p>
  );
}
