import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { ToolCard } from "@/components/ToolCard";
import { getMessages } from "@/i18n";
import { getCurrentUser } from "@/lib/auth/session";
import { TOOLS } from "@/lib/tools";
import { DashboardDataProvider, SavedPortfolioCount, StatusStrip } from "./DashboardStatus";

// The signed-in user's home. src/proxy.ts sends visitors without a session
// cookie to `/` before rendering; a stale cookie is caught here instead.

const t = getMessages();

export const metadata: Metadata = { title: t.dashboard.title };

async function Greeting() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  return (
    <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
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
          <h2 id="dashboard-tools-heading" className="text-xl font-semibold tracking-tight">
            {t.dashboard.tools.heading}
          </h2>
          <ul className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {TOOLS.map((tool) => (
              <li key={tool.slug}>
                <ToolCard tool={tool} personal={tool.slug === "portfolio" ? <SavedPortfolioCount /> : undefined} />
              </li>
            ))}
          </ul>
        </section>
      </DashboardDataProvider>
    </main>
  );
}
