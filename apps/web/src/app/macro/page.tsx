import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { parseCountries } from "./countries";
import { CrossCountry } from "./CrossCountry";
import { EuroArea } from "./EuroArea";
import { MacroTool } from "./MacroTool";

export const metadata: Metadata = { title: getMessages().tools["macro"].name };

// `?countries=USA,DEU,JPN` picks the economies to compare (the picker keeps it in sync).
async function Comparison({ searchParams }: { searchParams: PageProps<"/macro">["searchParams"] }) {
  const params = await searchParams;
  return <CrossCountry initialCountries={parseCountries(params.countries)} />;
}

export default function Page({ searchParams }: PageProps<"/macro">) {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-10">
      <ToolPageHeader tool="macro" title={t.tools.macro.name} intro={t.macro.intro} />
      {/* Reads the chart range and the added FRED series from the query string (shareable links). */}
      <Suspense>
        <MacroTool />
      </Suspense>
      <Suspense fallback={<div className="mt-10 h-96" />}>
        <Comparison searchParams={searchParams} />
      </Suspense>
      <EuroArea />
    </main>
  );
}
