import type { Metadata } from "next";
import { Suspense } from "react";
import { getMessages } from "@/i18n";
import { DEFAULT_TICKER } from "./defaults";
import { ValuationCalculator } from "./ValuationCalculator";

export const metadata: Metadata = { title: getMessages().tools["valuation"].name };

// `?ticker=MSFT` picks the company (the screener links here).
async function Calculator({ searchParams }: { searchParams: PageProps<"/valuation">["searchParams"] }) {
  const params = await searchParams;
  const raw = typeof params.ticker === "string" ? params.ticker.trim().toUpperCase() : "";
  const ticker = raw || DEFAULT_TICKER;
  return <ValuationCalculator key={ticker} initialTicker={ticker} />;
}

export default function Page({ searchParams }: PageProps<"/valuation">) {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.tools.valuation.name}</h1>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.valuation.intro}</p>
      <Suspense fallback={<p className="mt-6 text-sm text-black/60 dark:text-white/60">{t.valuation.loading}</p>}>
        <Calculator searchParams={searchParams} />
      </Suspense>
    </main>
  );
}
