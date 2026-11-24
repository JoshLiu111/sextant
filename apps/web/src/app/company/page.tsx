import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { CompanyRatios } from "./CompanyRatios";
import { CompanyStatements } from "./CompanyStatements";
import { FrequencyToggle } from "./FrequencyToggle";

export const metadata: Metadata = { title: getMessages().tools["company"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-10">
      <ToolPageHeader tool="company" title={t.tools.company.name} intro={t.company.intro} />
      {/* All read ?ticker= (links from the screener) and ?frequency=, known only at request time. */}
      <Suspense>
        <FrequencyToggle />
        <CompanyRatios />
        <CompanyStatements />
      </Suspense>
    </main>
  );
}
