import type { Metadata } from "next";
import { Suspense } from "react";
import { HowToUsePanel } from "@/components/HowToUsePanel";
import { getMessages } from "@/i18n";
import { PortfolioTool } from "./PortfolioTool";
import { SavedPortfoliosSection } from "./SavedPortfoliosSection";

export const metadata: Metadata = { title: getMessages().tools["portfolio"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.tools.portfolio.name}</h1>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.portfolio.intro}</p>
      <HowToUsePanel tool="portfolio" />
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
