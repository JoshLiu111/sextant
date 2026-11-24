import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { TOOL_PAGE } from "@/lib/layout";
import { ScreenerTool } from "./ScreenerTool";

export const metadata: Metadata = { title: getMessages().tools["screener"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main data-tool="screener" className={TOOL_PAGE}>
      <ToolPageHeader tool="screener" intro={t.screener.intro} />
      {/* The open tab and every tab's inputs come from the query string (shareable links). */}
      <Suspense>
        <ScreenerTool />
      </Suspense>
    </main>
  );
}
