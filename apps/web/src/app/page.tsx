import { ComputeStatus } from "@/components/ComputeStatus";
import { SignInLink } from "@/components/SignInLink";
import { ToolCardGroups } from "@/components/ToolCardGroups";
import { getMessages } from "@/i18n";

// The landing page. It never reads the session, so it stays static and
// cacheable; signing in from here starts at /auth/signin and returns to /.
export default function Home() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <section aria-labelledby="hero-heading" className="max-w-3xl">
        <h1 id="hero-heading" className="text-3xl font-medium tracking-tight sm:text-4xl">
          {t.home.hero.heading}
        </h1>
        <p data-testid="value-proposition" className="mt-3 text-lg text-ink-2">
          {t.home.hero.valueProposition}
        </p>
        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <a
            href="#tools"
            className="btn btn-primary text-center"
          >
            {t.home.hero.tryTool}
          </a>
          <SignInLink className="rounded-card border border-rule px-4 py-2 text-center text-sm font-medium hover:border-ink" />
        </div>
      </section>

      <section id="tools" aria-labelledby="tools-heading" className="mt-14 scroll-mt-4">
        <h2 id="tools-heading" className="text-3xl">
          {t.home.tools.heading}
        </h2>
        <p className="mt-1 text-ink-2">{t.home.tools.intro}</p>
        <div className="mt-6">
          <ToolCardGroups action="openDemo" />
        </div>
      </section>

      <section aria-labelledby="unlocks-heading" className="mt-14">
        <h2 id="unlocks-heading" className="text-3xl">
          {t.home.unlocks.heading}
        </h2>
        <p className="mt-1 text-ink-2">{t.home.unlocks.intro}</p>
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
