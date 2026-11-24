import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { PortfolioTool } from "./PortfolioTool";
import { SavedPortfoliosSection } from "./SavedPortfoliosSection";

export const metadata: Metadata = { title: getMessages().tools["portfolio"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-10">
      <ToolPageHeader tool="portfolio" title={t.tools.portfolio.name} intro={t.portfolio.intro} />
      {/* Reads the session cookie: signed-in users get their saved portfolios, visitors a sign-in prompt. */}
      <Suspense fallback={null}>
        <SavedPortfoliosSection />
      </Suspense>
      <section aria-labelledby="demo-portfolio" className="mt-10">
        <h2 id="demo-portfolio" className="text-xl font-semibold">
          {t.portfolio.demoHeading}
        </h2>
        {/* Reads the demo inputs from the query string (shareable links). */}
        <Suspense>
          <PortfolioTool />
        </Suspense>
      </section>
    </main>
  );
}
