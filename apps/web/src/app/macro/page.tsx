import type { Metadata } from "next";
import { Suspense } from "react";
import { ToolPageHeader } from "@/components/ToolPageHeader";
import { getMessages } from "@/i18n";
import { TOOL_PAGE } from "@/lib/layout";
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
    <main data-tool="macro" className={TOOL_PAGE}>
      <ToolPageHeader tool="macro" intro={t.macro.intro} />
      {/* Three sections, each with an anchor: #us, #countries (CrossCountry), #euro-area (EuroArea). */}
      <section id="us" aria-labelledby="macro-us" className="mt-6">
        <h2 id="macro-us" className="text-xl">
          {t.macro.sections.us}
        </h2>
        {/* Reads the chart range and the added FRED series from the query string (shareable links). */}
        <Suspense>
          <MacroTool />
        </Suspense>
      </section>
      <Suspense fallback={<div className="mt-10 h-96" />}>
        <Comparison searchParams={searchParams} />
      </Suspense>
      <EuroArea />
    </main>
  );
}
