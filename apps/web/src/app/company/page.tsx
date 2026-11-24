import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { TOOL_PAGE } from "@/lib/layout";
import { CompanyRatios } from "./CompanyRatios";
import { CompanyStatements } from "./CompanyStatements";
import { FrequencyToggle } from "./FrequencyToggle";

export const metadata: Metadata = { title: getMessages().tools["company"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main data-tool="company" className={TOOL_PAGE}>
      <ToolPageHeader tool="company" intro={t.company.intro} />
      {/* All read ?ticker= (links from the screener) and ?frequency=, known only at request time. */}
      <Suspense>
        <FrequencyToggle />
        <CompanyRatios />
        <CompanyStatements />
      </Suspense>
    </main>
  );
}
