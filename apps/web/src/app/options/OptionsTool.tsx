"use client";

import { useState } from "react";
import { getMessages } from "@/i18n";
import { AmericanPricer } from "./AmericanPricer";
import { OptionsCalculator } from "./OptionsCalculator";
import { StrategyBuilder } from "./StrategyBuilder";

const TABS = ["single", "strategy", "american"] as const;
type Tab = (typeof TABS)[number];

/** The Options Calculator's three views. Only the active one is mounted, so only it calls the API. */
export function OptionsTool() {
  const t = getMessages().options.tabs;
  const [tab, setTab] = useState<Tab>("single");

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
