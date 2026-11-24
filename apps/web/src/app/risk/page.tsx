import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { RiskTool } from "./RiskTool";

export const metadata: Metadata = { title: getMessages().tools["risk"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-10">
      <ToolPageHeader tool="risk" title={t.tools.risk.name} intro={t.risk.intro} />
      {/* Reads its inputs from the query string (shareable links). */}
      <Suspense>
        <RiskTool />
      </Suspense>
    </main>
  );
}
