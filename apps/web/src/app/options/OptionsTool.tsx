"use client";

import { useState } from "react";
import { getMessages } from "@/i18n";
import { useUrlInputs, type UrlCodec } from "@/lib/urlInputs";
import { AmericanPricer } from "./AmericanPricer";
import { OptionsCalculator } from "./OptionsCalculator";
import { StrategyBuilder } from "./StrategyBuilder";

const TABS = ["single", "strategy", "american"] as const;
type Tab = (typeof TABS)[number];

// Shareable links: `/options?tab=strategy&...`. The open tab is written when it
// changes; each tab writes its own inputs on submit. An unknown tab opens the first.
const TAB_CODEC: UrlCodec<{ tab: Tab }> = {
  keys: ["tab"],
  read: (params) => {
    const raw = params.get("tab");
    return { tab: TABS.find((id) => id === raw) ?? TABS[0] };
  },
  write: ({ tab }) => ({ tab }),
};

/**
 * The Options Calculator's three views. Only the active one is mounted, so only it calls the API.
 * Uses `useSearchParams` (via `useUrlInputs`), so render it inside `<Suspense>`.
 */
export function OptionsTool() {
  const t = getMessages().options.tabs;
  const { initial, share } = useUrlInputs(TAB_CODEC);
  const [tab, setTabState] = useState<Tab>(initial.tab);
  const setTab = (id: Tab) => {
    setTabState(id);
    share({ tab: id });
  };

  return (
    <div className="mt-6">
      <div role="tablist" aria-label={t.label} className="flex flex-wrap gap-1 border-b border-black/10 dark:border-white/15">
        {TABS.map((id) => (
          <button
            key={id}
            id={`options-tab-${id}`}
            role="tab"
            type="button"
            aria-selected={tab === id}
            aria-controls={`options-panel-${id}`}
            onClick={() => setTab(id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === id
                ? "border-black dark:border-white"
                : "border-transparent text-black/60 hover:text-black dark:text-white/60 dark:hover:text-white"
            }`}
          >
            {t[id]}
          </button>
        ))}
      </div>
      <div id={`options-panel-${tab}`} role="tabpanel" aria-labelledby={`options-tab-${tab}`}>
        {tab === "single" && <OptionsCalculator />}
        {tab === "strategy" && <StrategyBuilder />}
        {tab === "american" && <AmericanPricer />}
      </div>
    </div>
  );
}
