import Image from "next/image";
import { ComputeStatus } from "@/components/ComputeStatus";
import { SignInLink } from "@/components/SignInLink";
import { ToolCard } from "@/components/ToolCard";
import { getMessages } from "@/i18n";
import { TOOLS_BY_GROUP, type ToolGroup, type ToolSlug } from "@/lib/tools";
import { TrustTable } from "./TrustTable";

const ASSETS = "/landing/sextant-assets";

// Each tool's illustration (public/landing/sextant-assets/features), all 480 x 300.
const ART: Record<ToolSlug, { file: string; width: number; height: number }> = {
  macro: { file: "macro-dashboard", width: 480, height: 300 },
  screener: { file: "screener-calendar", width: 480, height: 300 },
  company: { file: "company-health-check", width: 480, height: 300 },
  valuation: { file: "valuation-calculator", width: 480, height: 300 },
  portfolio: { file: "my-portfolio", width: 480, height: 300 },
  risk: { file: "risk-performance", width: 480, height: 300 },
  options: { file: "options-calculator", width: 480, height: 300 },
  "ai-analyst": { file: "ai-analyst", width: 480, height: 300 },
};

// The four groups share one four-column grid: Markets and Companies take two columns
// each, then Portfolio & Risk three and AI Analyst one, so all eight cards are one size.
const SPAN: Record<ToolGroup, string> = {
  markets: "lg:col-span-2",
  companies: "lg:col-span-2",
  "portfolio-risk": "lg:col-span-3",
  "ai-analyst": "lg:col-span-1",
};
const COLS: Record<ToolGroup, string> = {
  markets: "md:grid-cols-2",
  companies: "md:grid-cols-2",
  "portfolio-risk": "md:grid-cols-2 lg:grid-cols-3",
  "ai-analyst": "md:grid-cols-2 lg:grid-cols-1",
};

// The landing page. It never reads the session, so it stays static and
// cacheable; signing in from here starts at /auth/signin and returns to /.
export default function Home() {
  const t = getMessages();

  return (
    <main className="w-full">
      {/* Hero: what Sextant is and the two ways in. Short, so the tools start on the first screen. */}
      <section aria-labelledby="hero-heading">
        <div className="mx-auto grid max-w-7xl items-center gap-x-16 gap-y-10 px-4 pb-14 pt-14 md:px-6 md:pt-20 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <div className="min-w-0">
            <h1 id="hero-heading" className="text-ink">
              {t.home.hero.heading}
            </h1>
            <p data-testid="value-proposition" className="lead mt-6 text-ink-2">
              {t.home.hero.valueProposition}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a href="#tools" className="btn btn-primary btn-lg">
                {t.home.hero.tryTool}
              </a>
              <SignInLink className="btn btn-lg" />
            </div>
          </div>
          <div className="art-plate hidden justify-self-center lg:block">
            <Image src={`${ASSETS}/illustrations/workspace.png`} width={800} height={740} alt="" priority sizes="22rem" className="block h-auto w-full max-w-[22rem]" />
          </div>
        </div>
      </section>

      {/* Every tool on one grid, grouped as the nav groups them. */}
      <section id="tools" aria-labelledby="tools-heading" className="scroll-mt-6">
        <div className="mx-auto max-w-7xl px-4 md:px-6">
          <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2 border-t border-ink pt-6">
            <h2 id="tools-heading" className="text-ink">
              {t.home.tools.heading}
            </h2>
            <p className="text-ink-2">{t.home.tools.intro}</p>
          </div>

          <div className="mt-10 grid grid-cols-1 gap-x-6 gap-y-12 md:grid-cols-2 lg:grid-cols-4">
            {TOOLS_BY_GROUP.map(({ group, tools }) => {
              const headingId = `tool-group-${group}`;
              return (
                <section key={group} aria-labelledby={headingId} data-group={group} className={`flex min-w-0 flex-col md:col-span-2 ${SPAN[group]}`}>
                  <h3 id={headingId} className="border-b border-rule pb-3 text-xl text-ink">
                    {t.toolGroups[group]}
                  </h3>
                  <ul className={`mt-5 grid grow grid-cols-1 gap-6 ${COLS[group]}`}>
                    {tools.map((tool) => {
                      const art = ART[tool.slug];
                      return (
                        <li key={tool.slug} className="min-w-0">
                          <ToolCard
                            tool={tool}
                            action="openDemo"
                            picture={
                              <div className="art-plate grid h-32 place-items-center">
                                <Image
                                  src={`${ASSETS}/features/${art.file}.png`}
                                  width={art.width}
                                  height={art.height}
                                  alt=""
                                  sizes="13rem"
                                  className="block h-full w-auto max-w-full object-contain"
                                />
                              </div>
                            }
                          />
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>
        </div>
      </section>

      {/* Signing in: what it adds, then what it keeps. */}
      <div className="mx-auto mt-24 grid max-w-7xl gap-x-16 gap-y-16 px-4 md:mt-32 md:px-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <section aria-labelledby="unlocks-heading" className="min-w-0">
          <h2 id="unlocks-heading" className="border-t border-ink pt-6 text-3xl text-ink">
            {t.home.unlocks.heading}
          </h2>
          <p className="mt-4 text-ink-2">{t.home.unlocks.intro}</p>
          <ul className="mt-6 border-t border-rule">
            {t.home.unlocks.items.map((item) => (
              <li key={item} className="border-b border-rule py-4 text-lg leading-snug text-ink">
                {item}
              </li>
            ))}
          </ul>
        </section>
        <TrustTable />
      </div>

      {/* Close: what Sextant is not, one action back to the tools, and whether the compute service is up. */}
      <section aria-labelledby="disclaimer-heading" className="mt-24 md:mt-32">
        <div className="mx-auto max-w-7xl px-4 md:px-6">
          <div className="grid items-center gap-x-16 gap-y-10 border-t border-ink pt-10 pb-20 md:pb-28 lg:grid-cols-[minmax(0,6fr)_minmax(0,6fr)]">
            <div className="min-w-0">
              <h2 id="disclaimer-heading" className="text-3xl text-ink">
                {t.home.disclaimer.heading}
              </h2>
              <p className="mt-4 max-w-[60ch] text-ink-2">{t.home.disclaimer.body}</p>
              <div className="mt-8 flex flex-wrap items-center gap-x-10 gap-y-6">
                <a href="#tools" className="btn btn-primary btn-lg">
                  {t.home.hero.tryTool}
                </a>
                <ComputeStatus />
              </div>
            </div>
            <div className="art-plate hidden min-w-0 lg:block">
              <Image src={`${ASSETS}/backgrounds/market-waves.png`} width={1300} height={290} alt="" sizes="(min-width: 64rem) 40vw, 100vw" className="block h-auto w-full" />
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
