import Link from "next/link";
import { ComputeStatus } from "@/components/ComputeStatus";
import { getMessages } from "@/i18n";
import { TOOLS } from "@/lib/tools";

export default function Home() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">{t.home.heading}</h1>
      <p className="mt-2 max-w-2xl text-black/70 dark:text-white/70">{t.home.intro}</p>
      <ul className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {TOOLS.map((tool) => (
          <li key={tool.slug} data-testid="tool-card">
            <Link
              href={tool.href}
              className="flex h-full flex-col rounded-lg border border-black/10 p-4 transition-colors hover:border-black/30 dark:border-white/15 dark:hover:border-white/40"
            >
              <h2 className="font-semibold">{t.tools[tool.slug].name}</h2>
              <p data-testid="tool-description" className="mt-1 text-sm text-black/70 dark:text-white/70">
                {t.tools[tool.slug].description}
              </p>
              {tool.status === "coming-soon" && (
                <span className="mt-3 self-start rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
                  {t.comingSoon.badge}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
      <div className="mt-10">
        <ComputeStatus />
      </div>
    </main>
  );
}
