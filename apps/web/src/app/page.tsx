import Image from "next/image";
import { Suspense } from "react";
import { ComputeStatus } from "@/components/ComputeStatus";
import { SignInLink } from "@/components/SignInLink";
import { getCurrentUser } from "@/lib/auth/session";
import { ToolCardGroups } from "@/components/ToolCardGroups";
import { getMessages } from "@/i18n";
import { FeatureBoards } from "./FeatureBoards";
import { MarketTape } from "./MarketTape";
import { TrustTable } from "./TrustTable";

const ASSETS = "/landing/sextant-assets";

/**
 * The hero's Sign in button, for visitors only. src/proxy.ts sends signed-in
 * users to /dashboard, but when its session check fails (a cold compute
 * service) they land here: the button then follows the same session read as
 * the nav's account menu, so the two always agree.
 */
async function HeroSignIn() {
  if (await getCurrentUser()) return null;
  return <SignInLink className="btn btn-lg" />;
}

// The landing page. Only the hero's Sign in button reads the session, behind
// Suspense, so the rest stays in the static, cacheable shell; signing in from
// here starts at /auth/signin and returns to /.
export default function Home() {
  const t = getMessages();

  return (
    <main className="w-full">
      {/* Live readings from the Macro Dashboard's cards, cached for hours; absent when the service is down.
          Streams in when it isn't in the prerendered page (any reading failed, as at build time). */}
      <div className="mt-3 md:mt-4">
        <Suspense fallback={null}>
          <MarketTape />
        </Suspense>
      </div>

      {/* Hero: what Sextant is and the two ways in. Short, so the tools start on the first screen. */}
      <section aria-labelledby="hero-heading">
        <div className="mx-auto grid max-w-7xl items-center gap-x-16 gap-y-10 px-4 pb-14 pt-12 md:px-6 md:pt-16 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
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
              <Suspense fallback={null}>
                <HeroSignIn />
              </Suspense>
            </div>
          </div>
          {/* Every group's features in turn, the workspace illustration blurred behind them. */}
          <div className="min-w-0">
            <FeatureBoards
              backdrop={<Image src={`${ASSETS}/illustrations/workspace.png`} width={800} height={740} alt="" priority sizes="40rem" />}
            />
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

          <div className="mt-10">
            <ToolCardGroups action="openDemo" />
          </div>
        </div>
      </section>

      {/* Signing in: what it adds, then what it keeps. */}
      <div className="mx-auto mt-16 grid max-w-7xl gap-x-16 gap-y-12 px-4 md:mt-20 md:px-6 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)]">
        <section aria-labelledby="unlocks-heading" className="min-w-0">
          <h2 id="unlocks-heading" className="border-t border-ink pt-5 text-2xl text-ink">
            {t.home.unlocks.heading}
          </h2>
          <p className="mt-2 text-ink-2">{t.home.unlocks.intro}</p>
          <ul className="mt-4 border-t border-rule">
            {t.home.unlocks.items.map((item) => (
              <li key={item} className="border-b border-rule py-2.5 leading-snug text-ink">
                {item}
              </li>
            ))}
          </ul>
        </section>
        <TrustTable />
      </div>

      {/* Close: what Sextant is not, one action back to the tools, and whether the compute service is up. */}
      <section aria-labelledby="disclaimer-heading" className="mt-16 md:mt-24">
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
