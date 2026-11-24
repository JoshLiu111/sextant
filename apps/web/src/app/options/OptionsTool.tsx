"use client";

import { Tabs, useUrlTab } from "@/components/Tabs";
import { getMessages } from "@/i18n";
import { AmericanPricer } from "./AmericanPricer";
import { OptionsCalculator } from "./OptionsCalculator";
import { StrategyBuilder } from "./StrategyBuilder";

// Shareable links: `/options?tab=strategy&...`. The open tab is written when it
// changes; each tab writes its own inputs on submit. An unknown tab opens the first.
const TABS = ["single", "strategy", "american"] as const;

/**
 * The Options Calculator's three views. Only the active one is mounted, so only it calls the API.
 * Uses `useSearchParams` (via `useUrlTab`), so render it inside `<Suspense>`.
 */
export function OptionsTool() {
  const t = getMessages().options.tabs;
  const [tab, setTab] = useUrlTab(TABS);

  return (
    <Tabs
      idPrefix="options"
      label={t.label}
      tabs={TABS}
      labels={t}
      className="mt-6"
      active={tab}
      onChange={setTab}
    >
      {tab === "single" && <OptionsCalculator />}
      {tab === "strategy" && <StrategyBuilder />}
      {tab === "american" && <AmericanPricer />}
    </Tabs>
  );
}
