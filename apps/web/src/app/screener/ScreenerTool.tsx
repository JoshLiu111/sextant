"use client";

import { Tabs, useUrlTab } from "@/components/Tabs";
import { getMessages } from "@/i18n";
import { DividendHistory } from "./DividendHistory";
import { EarningsCalendar } from "./EarningsCalendar";
import { LatestFilings } from "./LatestFilings";
import { Screener } from "./Screener";

// Shareable links: `/screener?tab=filings&filings_ticker=AAPL`. Each tab keeps
// its own prefixed inputs in the URL, so switching tabs loses none of them. An
// unknown or missing tab opens the screen.
const TABS = ["screen", "earnings", "dividends", "filings"] as const;

/**
 * The Screener & Calendar page's four sections. Only the open one is mounted,
 * so only it calls the API. Uses `useSearchParams`, so render it inside `<Suspense>`.
 */
export function ScreenerTool() {
  const t = getMessages().screener.tabs;
  const [tab, setTab] = useUrlTab(TABS);

  return (
    <Tabs
      idPrefix="screener"
      label={t.label}
      tabs={TABS.map((id) => ({ id, label: t[id] }))}
      active={tab}
      onChange={setTab}
    >
      {tab === "screen" && <Screener />}
      {tab === "earnings" && <EarningsCalendar />}
      {tab === "dividends" && <DividendHistory />}
      {tab === "filings" && <LatestFilings />}
    </Tabs>
  );
}
