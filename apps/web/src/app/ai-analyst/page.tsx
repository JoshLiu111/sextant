import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { AiAnalyst } from "./AiAnalyst";

export const metadata: Metadata = { title: getMessages().tools["ai-analyst"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main data-tool="ai-analyst" className="mx-auto w-full max-w-4xl px-4 pb-16 pt-10 md:px-6">
      <ToolPageHeader tool="ai-analyst" intro={t.analyst.intro} />
      {/* Reads the question from the query string (shareable links, "Try this" examples). */}
      <Suspense>
        <AiAnalyst />
      </Suspense>
    </main>
  );
}
