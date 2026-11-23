import type { Metadata } from "next";
import { getMessages } from "@/i18n";
import { LatestFilings } from "./LatestFilings";
import { Screener } from "./Screener";

export const metadata: Metadata = { title: getMessages().tools["screener"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.tools.screener.name}</h1>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.screener.intro}</p>
      <Screener />
      <LatestFilings />
    </main>
  );
}
