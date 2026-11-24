import { ComputeStatus } from "@/components/ComputeStatus";
import { ToolCard } from "@/components/ToolCard";
import { getMessages } from "@/i18n";
import { TOOLS } from "@/lib/tools";

// The landing page. It never reads the session, so it stays static and
// cacheable; signing in from here starts at /auth/signin and returns to /.
export default function Home() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <section aria-labelledby="hero-heading" className="max-w-3xl">
        <h1 id="hero-heading" className="text-3xl font-semibold tracking-tight sm:text-4xl">
          {t.home.hero.heading}
        </h1>
        <p data-testid="value-proposition" className="mt-3 text-lg text-black/70 dark:text-white/70">
          {t.home.hero.valueProposition}
        </p>
        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <a
            href="#tools"
            className="rounded bg-black px-4 py-2 text-center text-sm font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
          >
            {t.home.hero.tryTool}
          </a>
          {/* A full navigation (not <Link>): /auth/signin redirects off-site. */}
          <a
            href={`/auth/signin?returnTo=${encodeURIComponent("/")}`}
            className="rounded border border-black/15 px-4 py-2 text-center text-sm font-medium hover:border-black/40 dark:border-white/20 dark:hover:border-white/50"
          >
            {t.auth.signIn}
          </a>
        </div>
      </section>

      <section id="tools" aria-labelledby="tools-heading" className="mt-14 scroll-mt-4">
        <h2 id="tools-heading" className="text-2xl font-semibold tracking-tight">
          {t.home.tools.heading}
        </h2>
        <p className="mt-1 text-black/70 dark:text-white/70">{t.home.tools.intro}</p>
        <ul className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {TOOLS.map((tool) => (
            <li key={tool.slug}>
              <ToolCard tool={tool} />
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="unlocks-heading" className="mt-14">
        <h2 id="unlocks-heading" className="text-2xl font-semibold tracking-tight">
          {t.home.unlocks.heading}
        </h2>
        <p className="mt-1 text-black/70 dark:text-white/70">{t.home.unlocks.intro}</p>
        <ul className="mt-4 flex list-disc flex-col gap-2 pl-5">
          {t.home.unlocks.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <div className="mt-14">
        <ComputeStatus />
      </div>
    </main>
  );
}
