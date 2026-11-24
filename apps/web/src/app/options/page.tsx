import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { OptionsTool } from "./OptionsTool";

export const metadata: Metadata = { title: getMessages().tools["options"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-10">
      <ToolPageHeader tool="options" title={t.tools.options.name} intro={t.options.intro} />
      {/* Reads its inputs (and the open tab) from the query string (shareable links). */}
      <Suspense>
        <OptionsTool />
      </Suspense>
    </main>
  );
}
