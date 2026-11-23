import type { Metadata } from "next";
import { getMessages } from "@/i18n";
import { MacroDashboard } from "./MacroDashboard";
import { TreasuryRates } from "./TreasuryRates";

export const metadata: Metadata = { title: getMessages().tools["macro"].name };

export default function Page() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.tools.macro.name}</h1>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.macro.intro}</p>
      <MacroDashboard />
      <TreasuryRates />
    </main>
  );
}
