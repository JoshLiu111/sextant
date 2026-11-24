import { hrefWithQuery } from "@/lib/urlInputs";
import type { ToolGroup, ToolSlug } from "@/lib/tools";

// The hero's boards: nine features per tool group, each a link that opens the tool
// at that feature. Links follow the "Try this" format (lib/howToUse.ts): the tool's
// own URL inputs, then `#target`, the element the page scrolls to once it settles.
export type Feature = { tool: ToolSlug; label: string; href: string };

const at = (path: string, params: Record<string, string>, target: string) => `${hrefWithQuery(path, params)}#${target}`;
const ask = (question: string): Feature => ({ tool: "ai-analyst", label: question, href: at("/ai-analyst", { question }, "analyst") });

export const FEATURE_BOARDS: Record<ToolGroup, readonly Feature[]> = {
  markets: [
    { tool: "macro", label: "US inflation, jobs and growth", href: "/macro#us" },
    { tool: "macro", label: "The Treasury yield curve", href: "/macro#macro-rates" },
    { tool: "macro", label: "The US, China and India side by side", href: at("/macro", { countries: "USA,CHN,IND" }, "countries") },
    { tool: "macro", label: "Euro area rates and inflation", href: "/macro#euro-area" },
    { tool: "macro", label: "US payrolls since 2020", href: at("/macro", { series: "PAYEMS", start: "2020-01-01" }, "macro-custom") },
    {
      tool: "screener",
      label: "Growing companies with little debt",
      href: at("/screener", { criteria: "revenue_growth:min:10,debt_ratio:max:30", sort: "ticker", direction: "asc" }, "screen-heading"),
    },
    { tool: "screener", label: "The earnings calendar", href: at("/screener", { tab: "earnings" }, "screener-tab-earnings") },
    { tool: "screener", label: "JPMorgan's dividend history", href: at("/screener", { tab: "dividends", dividends_ticker: "JPM" }, "dividends-section") },
    { tool: "screener", label: "The latest SEC filings", href: at("/screener", { tab: "filings" }, "screener-tab-filings") },
  ],
  companies: [
    { tool: "company", label: "Core ratios over several years", href: "/company#ratios-heading" },
    { tool: "company", label: "Apple's P/E at a $250 share price", href: at("/company", { companies: "AAPL:250" }, "ratios-valuation") },
    { tool: "company", label: "Microsoft beside Apple", href: at("/company", { companies: "MSFT,AAPL", ticker: "MSFT" }, "ratios-heading") },
    { tool: "company", label: "Statements from SEC filings", href: "/company#company-inputs" },
    { tool: "valuation", label: "Microsoft's value at 8% growth", href: at("/valuation", { ticker: "MSFT", growth_rate: "8" }, "valuation-tab-overview") },
    { tool: "valuation", label: "A step-by-step WACC", href: at("/valuation", { tab: "wacc" }, "valuation-tab-wacc") },
    {
      tool: "valuation",
      label: "The cost of equity set to 12%",
      href: at("/valuation", { tab: "wacc", ticker: "MSFT", cost_of_equity: "12" }, "valuation-tab-wacc"),
    },
    { tool: "valuation", label: "A sensitivity table", href: "/valuation#sensitivity-heading" },
    { tool: "valuation", label: "Inputs read from the 10-K", href: at("/valuation", { tab: "statement" }, "valuation-tab-statement") },
  ],
  "portfolio-risk": [
    { tool: "portfolio", label: "A 60/40 portfolio", href: at("/portfolio", { holdings: "DEMO-C:60,DEMO-E:40" }, "portfolio-tab-overview") },
    { tool: "portfolio", label: "A rebalancing backtest", href: at("/portfolio", { tab: "rebalancing" }, "portfolio-tab-rebalancing") },
    { tool: "portfolio", label: "The efficient frontier", href: at("/portfolio", { tab: "frontier" }, "portfolio-tab-frontier") },
    { tool: "risk", label: "A 45% crash, measured", href: at("/risk", { tickers: "DEMO-D", start: "2022-02-28", end: "2022-04-11" }, "risk-tab-overview") },
    { tool: "risk", label: "Two stocks at 99% VaR", href: at("/risk", { tickers: "DEMO-A,DEMO-B", confidence: "99" }, "risk-tab-overview") },
    { tool: "risk", label: "Rolling volatility and returns", href: at("/risk", { tab: "rolling" }, "risk-tab-rolling") },
    { tool: "risk", label: "Technical analysis", href: at("/risk", { tab: "technical" }, "risk-tab-technical") },
    { tool: "options", label: "A call at 30% volatility", href: at("/options", { volatility: "30" }, "options-tab-single") },
    {
      tool: "options",
      label: "An iron condor's payoff",
      href: at("/options", { tab: "strategy", legs: "put:long:1:80,put:short:1:90,call:short:1:110,call:long:1:120" }, "options-tab-strategy"),
    },
  ],
  // Each question maps onto one of the calculations the AI Analyst can call.
  "ai-analyst": [
    ask("What is an at-the-money one-year call worth?"),
    ask("How risky is AAPL compared with the S&P 500?"),
    ask("Compare the financial health of MSFT and GOOGL"),
    ask("What is Microsoft worth on a DCF?"),
    ask("Where are US inflation and unemployment now?"),
    ask("Is the Treasury yield curve inverted?"),
    ask("Which companies grow fast with little debt?"),
    ask("How did a 60/40 mix of SPY and TLT do?"),
    ask("What does a bull call spread pay at expiry?"),
  ],
};
