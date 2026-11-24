import type { Metadata } from "next";
import { Suspense } from "react";
import { HowToUsePanel } from "@/components/HowToUsePanel";
import { getMessages } from "@/i18n";
import { OptionsTool } from "./OptionsTool";

export const metadata: Metadata = { title: getMessages().tools["options"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.tools.options.name}</h1>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.options.intro}</p>
      <HowToUsePanel tool="options" />
      {/* Reads its inputs (and the open tab) from the query string (shareable links). */}
      <Suspense>
        <OptionsTool />
      </Suspense>
    </main>
  );
}
