"use client";

// The Demo data / My data seam shared by every market-data tool. A tool's
// request carries `source`: "synthetic" (Demo data, anyone) or a My data
// provider id, which the compute service runs on the signed-in user's own key
// (apps/compute/sextant_compute/data/sources.py `PriceSource`). A new provider
// goes in the registry in `providerKeys.ts`; `DataModeToggle` then offers it, and
// with several keys the user picks one ("My data (Tiingo)" / "My data (FMP)").

import { useEffect, useState } from "react";
import { PROVIDER_NAMES, PROVIDERS, providerKeysApi, type Provider } from "./providerKeys";

export { PROVIDER_NAMES };

/** Providers that can back My data, in display order: every key provider has a daily-prices adapter. */
export const MY_DATA_PROVIDERS: readonly Provider[] = PROVIDERS;

export type MyDataProvider = Provider;

export const DEMO_SOURCE = "synthetic";

/** Demo tickers (DEMO-A, DEMO-MKT, ...) only have Demo data (compute `data/sources.py` `is_demo_ticker`). */
export const isDemoTicker = (ticker: string) => ticker.trim().toUpperCase().startsWith("DEMO-");

/** What a market-data request's `source` field may say. */
export type PriceSource = typeof DEMO_SOURCE | MyDataProvider;


/**
 * The My data providers the visitor has a saved key for, in display order.
 * Empty for anonymous visitors, users without a key, and while loading, so the
 * tool starts (and stays) on demo data until a key is known to exist.
 */
export function useMyDataProviders(): MyDataProvider[] {
  return useMyDataProviderList().providers;
}

/** `useMyDataProviders`, plus whether the key list has answered yet (`loaded`). */
export function useMyDataProviderList(): { providers: MyDataProvider[]; loaded: boolean } {
  const [state, setState] = useState<{ providers: MyDataProvider[]; loaded: boolean }>({
    providers: [],
    loaded: false,
  });
  useEffect(() => {
    let live = true;
    providerKeysApi.list().then((outcome) => {
      if (!live) return;
      if (outcome.kind !== "ok") return setState({ providers: [], loaded: true }); // 401 when signed out
      const saved = new Set(outcome.value.map((k) => k.provider));
      setState({ providers: MY_DATA_PROVIDERS.filter((p) => saved.has(p)), loaded: true });
    });
    return () => {
      live = false;
    };
  }, []);
  return state;
}
