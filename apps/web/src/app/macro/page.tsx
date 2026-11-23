import type { Metadata } from "next";
import { Suspense } from "react";
import { getMessages } from "@/i18n";
import { parseCountries } from "./countries";
import { CrossCountry } from "./CrossCountry";
import { EuroArea } from "./EuroArea";
import { MacroDashboard } from "./MacroDashboard";
import { TreasuryRates } from "./TreasuryRates";

export const metadata: Metadata = { title: getMessages().tools["macro"].name };

// `?countries=USA,DEU,JPN` picks the economies to compare (the picker keeps it in sync).
async function Comparison({ searchParams }: { searchParams: PageProps<"/macro">["searchParams"] }) {
  const params = await searchParams;
  return <CrossCountry initialCountries={parseCountries(params.countries)} />;
}

export default function Page({ searchParams }: PageProps<"/macro">) {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.tools.macro.name}</h1>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.macro.intro}</p>
      <MacroDashboard />
      <TreasuryRates />
      <Suspense fallback={<div className="mt-10 h-96" />}>
        <Comparison searchParams={searchParams} />
      </Suspense>
      <EuroArea />
    </main>
  );
}
