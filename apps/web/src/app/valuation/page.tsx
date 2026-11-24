import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { ValuationCalculator } from "./ValuationCalculator";

export const metadata: Metadata = { title: getMessages().tools["valuation"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-10">
      <ToolPageHeader tool="valuation" title={t.tools.valuation.name} intro={t.valuation.intro} />
      {/* Reads its inputs from the query string: `?ticker=MSFT` (screener links) and the assumptions. */}
      <Suspense fallback={<p className="mt-6 text-sm text-black/60 dark:text-white/60">{t.valuation.loading}</p>}>
        <ValuationCalculator />
      </Suspense>
    </main>
  );
}
