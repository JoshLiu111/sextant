import type { Metadata } from "next";
import { Suspense } from "react";
import { HowToUsePanel } from "@/components/HowToUsePanel";
import { getMessages } from "@/i18n";
import { ValuationCalculator } from "./ValuationCalculator";

export const metadata: Metadata = { title: getMessages().tools["valuation"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.tools.valuation.name}</h1>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.valuation.intro}</p>
      <HowToUsePanel tool="valuation" />
      {/* Reads its inputs from the query string: `?ticker=MSFT` (screener links) and the assumptions. */}
      <Suspense fallback={<p className="mt-6 text-sm text-black/60 dark:text-white/60">{t.valuation.loading}</p>}>
        <ValuationCalculator />
      </Suspense>
    </main>
  );
}
