import type { Metadata } from "next";
import { Suspense } from "react";
import { getMessages } from "@/i18n";
import { RiskTool } from "./RiskTool";

export const metadata: Metadata = { title: getMessages().tools["risk"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.tools.risk.name}</h1>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.risk.intro}</p>
      {/* Reads its inputs from the query string (shareable links). */}
      <Suspense>
        <RiskTool />
      </Suspense>
    </main>
  );
}
