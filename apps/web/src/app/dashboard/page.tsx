import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { ToolCardGroups } from "@/components/ToolCardGroups";
import { getMessages } from "@/i18n";
import { getCurrentUser } from "@/lib/auth/session";
import { DashboardDataProvider, SavedPortfolioCount, StatusStrip } from "./DashboardStatus";

// The signed-in user's home. src/proxy.ts sends visitors without a session
// cookie to `/` before rendering; a stale cookie is caught here instead.

const t = getMessages();

export const metadata: Metadata = { title: t.dashboard.title };

async function Greeting() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  return (
    <h1 className="text-2xl font-medium tracking-tight sm:text-3xl">
      {t.dashboard.greeting(user.name || user.email)}
    </h1>
  );
}

export default function DashboardPage() {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <Suspense fallback={<div className="h-9" aria-hidden />}>
        <Greeting />
      </Suspense>
      <DashboardDataProvider>
        <div className="mt-6">
          <StatusStrip />
        </div>
        <section aria-labelledby="dashboard-tools-heading" className="mt-10">
          <h2 id="dashboard-tools-heading" className="text-2xl">
            {t.dashboard.tools.heading}
          </h2>
          <div className="mt-4">
            <ToolCardGroups
              action="open"
              personal={(tool) => (tool.slug === "portfolio" ? <SavedPortfolioCount /> : undefined)}
            />
          </div>
        </section>
      </DashboardDataProvider>
    </main>
  );
}
