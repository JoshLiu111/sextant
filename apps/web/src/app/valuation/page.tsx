import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { TOOL_PAGE } from "@/lib/layout";
import { ValuationCalculator } from "./ValuationCalculator";

export const metadata: Metadata = { title: getMessages().tools["valuation"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main data-tool="valuation" className={TOOL_PAGE}>
      <ToolPageHeader tool="valuation" intro={t.valuation.intro} />
      {/* Reads its inputs from the query string: `?ticker=MSFT` (screener links) and the assumptions. */}
      <Suspense fallback={<p className="mt-6 text-sm text-muted">{t.valuation.loading}</p>}>
        <ValuationCalculator />
      </Suspense>
    </main>
  );
}
