import type { Metadata } from "next";
import { Suspense } from "react";
import { HowToUsePanel } from "@/components/HowToUsePanel";
import { getMessages } from "@/i18n";
import { CompanyRatios } from "./CompanyRatios";
import { CompanyStatements } from "./CompanyStatements";
import { FrequencyToggle } from "./FrequencyToggle";

export const metadata: Metadata = { title: getMessages().tools["company"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.tools.company.name}</h1>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.company.intro}</p>
      <HowToUsePanel tool="company" />
      {/* All read ?ticker= (links from the screener) and ?frequency=, known only at request time. */}
      <Suspense>
        <FrequencyToggle />
        <CompanyRatios />
        <CompanyStatements />
      </Suspense>
    </main>
  );
}
