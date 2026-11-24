import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { ScreenerTool } from "./ScreenerTool";

export const metadata: Metadata = { title: getMessages().tools["screener"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-10">
      <ToolPageHeader tool="screener" title={t.tools.screener.name} intro={t.screener.intro} />
      {/* The open tab and every tab's inputs come from the query string (shareable links). */}
      <Suspense>
        <ScreenerTool />
      </Suspense>
    </main>
  );
}
