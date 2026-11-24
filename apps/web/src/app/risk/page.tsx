import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { TOOL_PAGE } from "@/lib/layout";
import { RiskTool } from "./RiskTool";

export const metadata: Metadata = { title: getMessages().tools["risk"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className={TOOL_PAGE}>
      <ToolPageHeader tool="risk" intro={t.risk.intro} />
      {/* Reads its inputs from the query string (shareable links). */}
      <Suspense>
        <RiskTool />
      </Suspense>
    </main>
  );
}
