import type { Metadata } from "next";
import Image from "next/image";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { ToolCardGroups } from "@/components/ToolCardGroups";
import { getMessages } from "@/i18n";
import { getCurrentUser } from "@/lib/auth/session";
import { FeatureBoards } from "../FeatureBoards";
import { MarketTape } from "../MarketTape";
import { DashboardDataProvider, SavedPortfolioCount, StatusStrip } from "./DashboardStatus";

// The signed-in user's home, built from the landing page's parts: the tape, a
// split hero (the greeting and the account's status beside the feature boards)
// and the same illustrated tool grid, each card opening the tool. src/proxy.ts
// sends visitors without a session cookie to `/` before rendering; a stale
// cookie is caught here instead.

const t = getMessages();

export const metadata: Metadata = { title: t.dashboard.title };

async function Greeting() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  return (
    <h1 id="dashboard-heading" className="text-display-s text-ink">
      {t.dashboard.greeting(user.name || user.email)}
    </h1>
  );
}

export default function DashboardPage() {
  return (
    <main className="w-full pb-20 md:pb-28">
      {/* The landing's live readings from the Macro Dashboard's cards. */}
      <div className="mt-3 md:mt-4">
        <Suspense fallback={null}>
          <MarketTape />
        </Suspense>
      </div>

      <DashboardDataProvider>
        <section aria-labelledby="dashboard-heading">
          <div className="mx-auto grid max-w-7xl items-center gap-x-16 gap-y-10 px-4 pb-14 pt-12 md:px-6 md:pt-16 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <div className="min-w-0">
              <Suspense fallback={<div className="h-24" aria-hidden />}>
                <Greeting />
              </Suspense>
              <p className="lead mt-6 text-ink-2">{t.dashboard.lead}</p>
              <div className="mt-8">
                <StatusStrip />
              </div>
            </div>
            <div className="min-w-0">
              <FeatureBoards
                backdrop={
                  <Image src="/landing/sextant-assets/illustrations/workspace.png" width={800} height={740} alt="" priority sizes="40rem" />
                }
              />
            </div>
          </div>
        </section>

        <section aria-labelledby="dashboard-tools-heading">
          <div className="mx-auto max-w-7xl px-4 md:px-6">
            <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2 border-t border-ink pt-6">
              <h2 id="dashboard-tools-heading" className="text-ink">
                {t.dashboard.tools.heading}
              </h2>
              <p className="text-ink-2">{t.dashboard.tools.intro}</p>
            </div>
            <div className="mt-10">
              <ToolCardGroups
                action="open"
                personal={(tool) => (tool.slug === "portfolio" ? <SavedPortfolioCount /> : undefined)}
              />
            </div>
          </div>
        </section>
      </DashboardDataProvider>
    </main>
  );
}
