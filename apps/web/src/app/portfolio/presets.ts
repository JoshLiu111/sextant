import type { Messages } from "@/i18n";

/** A holding as the form keeps it: weight in percent, as typed. */
export type HoldingInput = { ticker: string; weight: string };

export type PresetId = keyof Messages["portfolio"]["presets"]["items"];

/** Classic allocations mapped onto demo tickers (names and descriptions in en.ts). */
export const PRESETS: Record<PresetId, readonly HoldingInput[]> = {
  sixtyForty: [
    { ticker: "DEMO-C", weight: "60" },
    { ticker: "DEMO-E", weight: "40" },
  ],
  allWeather: [
    { ticker: "DEMO-C", weight: "30" },
    { ticker: "DEMO-E", weight: "55" },
    { ticker: "DEMO-A", weight: "7.5" },
    { ticker: "DEMO-F", weight: "7.5" },
  ],
};

/** What the page shows on first load. */
export const DEFAULT_HOLDINGS: readonly HoldingInput[] = [
  { ticker: "DEMO-A", weight: "40" },
  { ticker: "DEMO-B", weight: "30" },
  { ticker: "DEMO-E", weight: "30" },
];
