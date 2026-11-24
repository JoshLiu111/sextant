import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { TOOL_PAGE } from "@/lib/layout";
import { PortfolioTool } from "./PortfolioTool";
import { SavedPortfoliosSection } from "./SavedPortfoliosSection";

export const metadata: Metadata = { title: getMessages().tools["portfolio"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main data-tool="portfolio" className={TOOL_PAGE}>
      <ToolPageHeader tool="portfolio" intro={t.portfolio.intro} />
      {/* Reads the session cookie: signed-in users get their saved portfolios, visitors a sign-in prompt. */}
      <Suspense fallback={null}>
        <SavedPortfoliosSection />
      </Suspense>
      <section aria-labelledby="demo-portfolio" className="mt-10">
        <h2 id="demo-portfolio" className="text-2xl">
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
