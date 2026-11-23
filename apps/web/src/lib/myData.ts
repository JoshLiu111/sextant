"use client";

// The Demo data / My data seam shared by every market-data tool. A tool's
// request carries `source`: "synthetic" (Demo data, anyone) or a My data
// provider id, which the compute service runs on the signed-in user's own key
// (apps/compute/sextant_compute/data/sources.py `PriceSource`). Add FMP here
// when its adapter lands; `DataModeToggle` then offers it automatically.

import { useEffect, useState } from "react";
import { providerKeysApi, type Provider } from "./providerKeys";

/** Providers that can back My data (have a daily-prices adapter), in display order. */
export const MY_DATA_PROVIDERS = ["tiingo"] as const satisfies readonly Provider[];

export type MyDataProvider = (typeof MY_DATA_PROVIDERS)[number];

export const DEMO_SOURCE = "synthetic";

/** What a market-data request's `source` field may say. */
export type PriceSource = typeof DEMO_SOURCE | MyDataProvider;

export const PROVIDER_NAMES: Record<MyDataProvider, string> = { tiingo: "Tiingo" };

/**
 * The My data providers the visitor has a saved key for, in display order.
 * Empty for anonymous visitors, users without a key, and while loading, so the
 * tool starts (and stays) on demo data until a key is known to exist.
 */
export function useMyDataProviders(): MyDataProvider[] {
  const [providers, setProviders] = useState<MyDataProvider[]>([]);
  useEffect(() => {
    let live = true;
    providerKeysApi.list().then((outcome) => {
      if (!live || outcome.kind !== "ok") return; // 401 when signed out
      const saved = new Set(outcome.value.map((k) => k.provider));
      setProviders(MY_DATA_PROVIDERS.filter((p) => saved.has(p)));
    });
    return () => {
      live = false;
    };
  }, []);
  return providers;
}
