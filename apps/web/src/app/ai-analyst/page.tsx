import type { Metadata } from "next";
import { getMessages } from "@/i18n";
import { AiAnalyst } from "./AiAnalyst";

export const metadata: Metadata = { title: getMessages().tools["ai-analyst"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.tools["ai-analyst"].name}</h1>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.analyst.intro}</p>
      <AiAnalyst />
    </main>
  );
}
