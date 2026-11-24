"use client";

import { Tabs, useUrlTab, type TabParams } from "@/components/Tabs";
import { getMessages } from "@/i18n";
import { DIVIDENDS_PARAMS, DividendHistory } from "./DividendHistory";
import { EARNINGS_PARAMS, EarningsCalendar } from "./EarningsCalendar";
import { FILINGS_PARAMS, LatestFilings } from "./LatestFilings";
import { Screener } from "./Screener";

// Shareable links: `/screener?tab=filings&filings_ticker=AAPL`. Each tab keeps
// its own prefixed inputs in the URL, so switching tabs loses none of them. An
// unknown tab opens the screen; a link without `tab=` (shared before the page
// had tabs) opens the tab whose params it carries.
const TABS = ["screen", "earnings", "dividends", "filings"] as const;
const TAB_PARAMS: TabParams<(typeof TABS)[number]> = {
  earnings: EARNINGS_PARAMS,
  dividends: DIVIDENDS_PARAMS,
  filings: FILINGS_PARAMS,
};

/**
 * The Screener & Calendar page's four sections. Only the open one is mounted,
 * so only it calls the API. Uses `useSearchParams`, so render it inside `<Suspense>`.
 */
export function ScreenerTool() {
  const t = getMessages().screener.tabs;
  const [tab, setTab] = useUrlTab(TABS, { inferFrom: TAB_PARAMS });

  return (
    <Tabs idPrefix="screener" label={t.label} tabs={TABS} labels={t} active={tab} onChange={setTab} className="mt-6">
      {tab === "screen" && <Screener />}
      {tab === "earnings" && <EarningsCalendar />}
      {tab === "dividends" && <DividendHistory />}
      {tab === "filings" && <LatestFilings />}
    </Tabs>
  );
}
