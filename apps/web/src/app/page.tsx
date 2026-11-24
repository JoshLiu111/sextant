import type { ReactNode } from "react";
import { ComputeStatus } from "@/components/ComputeStatus";
import { SignInLink } from "@/components/SignInLink";
import { ToolCard } from "@/components/ToolCard";
import { getMessages, type Messages } from "@/i18n";
import { getTool, TOOLS_BY_GROUP, type ToolGroup, type ToolSlug } from "@/lib/tools";
import { HomeFigure, ProductPicture } from "./HomeFigure";
import { MethodsBand, type MethodRun } from "./MethodsBand";
import { ProofDeck, type DeckFrame } from "./ProofDeck";

// The hero deck: one capture per charted tool, in the nav's order. Sizes are the
// files' own pixels in /public/landing (2x captures).
const DECK: { id: keyof Messages["home"]["figures"]; tool: ToolSlug; width: number; height: number }[] = [
  { id: "yieldCurve", tool: "macro", width: 1968, height: 1283 },
  { id: "earnings", tool: "screener", width: 1688, height: 986 },
  { id: "profitability", tool: "company", width: 1464, height: 1308 },
  { id: "sensitivity", tool: "valuation", width: 1824, height: 1223 },
  { id: "frontier", tool: "portfolio", width: 1768, height: 838 },
  { id: "correlation", tool: "risk", width: 1017, height: 657 },
  { id: "condor", tool: "options", width: 1400, height: 1175 },
];
const FILE: Partial<Record<keyof Messages["home"]["figures"], string>> = { yieldCurve: "yield-card" };

// The methods tape: markets and companies on the first row, portfolio and risk on the second.
const TAPE_ROWS: ToolSlug[][] = [
  ["macro", "screener", "company", "valuation"],
  ["portfolio", "risk", "options"],
];

// The landing page. It never reads the session, so it stays static and
// cacheable; signing in from here starts at /auth/signin and returns to /.
export default function Home() {
  const t = getMessages();
  const f = t.home.figures;

  // Each tool group is a question block: its tools' cards with a capture of one
  // of their own charts (AI Analyst has no chart of its own, so it is set in type).
  const deck: DeckFrame[] = DECK.map(({ id, tool, width, height }) => {
    const copy = f[id] as { short: string; caption: string; alt: string; source: string; note: string };
    return {
      id,
      tool,
      href: getTool(tool).href,
      name: t.tools[tool].name,
      short: copy.short,
      caption: copy.caption,
      showLabel: t.home.deck.show(t.tools[tool].name),
      openLabel: t.home.deck.open(t.tools[tool].name),
      source: copy.source,
      note: copy.note,
      ratio: width / height,
      picture: (
        <ProductPicture
          name={FILE[id] ?? id}
          width={width}
          height={height}
          alt={copy.alt}
          priority={id === "yieldCurve"}
          sizes="(min-width: 64rem) 46vw, 100vw"
        />
      ),
      overlay:
        id === "yieldCurve" ? (
          // Redlines at the 2- and 10-year maturities, up to the 10-year yield: the gap
          // between the line and the 2-year point is the term spread.
          <div aria-hidden className="pointer-events-none absolute inset-0">
            <span className="guide guide-y" style={{ left: "13%", top: "62.9%", bottom: "14.3%" }} />
            <span className="guide guide-y" style={{ left: "36.9%", top: "62.9%", bottom: "14.3%" }} />
            <span className="guide guide-x" style={{ left: "13%", right: "63.1%", top: "62.9%" }} />
            <span className="guide-label guide-chip" style={{ left: "13%", top: "calc(62.9% - 1.75rem)" }}>
              {f.yieldCurve.spread}
            </span>
          </div>
        ) : undefined,
    };
  });
  const tape: MethodRun[][] = TAPE_ROWS.map((row) =>
    row.map((tool) => ({ tool, name: t.tools[tool].name, methods: t.home.methods.groups[tool as keyof typeof t.home.methods.groups] })),
  );

  const figures: Partial<Record<ToolGroup, ReactNode>> = {
    markets: <HomeFigure name="countries" width={1272} height={604} alt={f.countries.alt} caption={f.countries.caption} />,
    companies: <HomeFigure name="income" width={2528} height={786} alt={f.income.alt} caption={f.income.caption} />,
    "portfolio-risk": <HomeFigure name="underwater" width={1824} height={682} alt={f.underwater.alt} caption={f.underwater.caption} />,
  };

  return (
    <main className="w-full">
      {/* Hero: the claim and its proof, a real chart with the construction that made it. */}
      <section aria-labelledby="hero-heading" className="proof-fade">
        <div className="mx-auto grid max-w-7xl items-center gap-x-16 gap-y-10 px-4 pb-16 pt-14 md:px-6 lg:min-h-[calc(100svh-5.5rem)] lg:pt-16 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:pb-20">
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
          <ProofDeck
            frames={deck}
            label={t.home.deck.label}
            pauseLabel={t.home.deck.pause}
            playLabel={t.home.deck.play}
            className="mt-14 w-full sm:px-4 lg:mt-0 lg:w-[min(100%,calc((100svh-22rem)*4/3))] lg:justify-self-end lg:px-0"
          />
        </div>
      </section>

      <MethodsBand heading={t.home.methods.heading} rows={tape} pauseLabel={t.home.methods.pause} playLabel={t.home.methods.play} />

      <section id="tools" aria-labelledby="tools-heading" className="scroll-mt-6 pt-24 md:pt-32">
        <div className="mx-auto max-w-7xl px-4 md:px-6">
          <div className="grid gap-x-8 gap-y-4 border-t border-ink pt-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-end">
            <h2 id="tools-heading" className="text-ink">
              {t.home.tools.heading}
            </h2>
            <p className="lead text-ink-2">{t.home.tools.intro}</p>
          </div>

          <div className="mt-16 flex flex-col gap-28 md:mt-20 md:gap-36">
            {TOOLS_BY_GROUP.map(({ group, tools }) => {
              const headingId = `tool-group-${group}`;
              const figure = figures[group];
              const cards = (cols: string, wide = false) => (
                <ul className={`grid grid-cols-1 gap-6 ${cols}`}>
                  {tools.map((tool) => (
                    <li key={tool.slug}>
                      <ToolCard tool={tool} action="openDemo" wide={wide} />
                    </li>
                  ))}
                </ul>
              );
              // One composition per group, never the same twice in a row.
              const body =
                group === "markets" ? (
                  // Split: the chart beside the two cards.
                  <div className="grid items-center gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
                    {figure}
                    {cards("")}
                  </div>
                ) : group === "companies" ? (
                  // The two cards, then the table across the width.
                  <div className="flex flex-col gap-14">
                    {cards("md:grid-cols-2")}
                    {figure}
                  </div>
                ) : group === "portfolio-risk" ? (
                  // Showcase: the chart across the width, the three cards beneath.
                  <div className="flex flex-col gap-12">
                    {figure}
                    {cards("md:grid-cols-3")}
                  </div>
                ) : (
                  // Type only: the one card laid across the row.
                  cards("", true)
                );
              return (
                <section key={group} aria-labelledby={headingId} data-group={group}>
                  <h3 id={headingId} className="text-2xl text-ink md:text-3xl">
                    {t.toolGroups[group]}
                  </h3>
                  <div className="mt-10">{body}</div>
                </section>
              );
            })}
          </div>
        </div>
      </section>

      <section aria-labelledby="unlocks-heading" className="mt-28 bg-paper-2 py-20 md:mt-36 md:py-28">
        <div className="mx-auto grid max-w-7xl gap-x-8 gap-y-8 px-4 md:px-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div>
            <h2 id="unlocks-heading" className="text-ink">
              {t.home.unlocks.heading}
            </h2>
            <p className="mt-5 max-w-[40ch] text-ink-2">{t.home.unlocks.intro}</p>
          </div>
          <ul className="border-t border-ink">
            {t.home.unlocks.items.map((item) => (
              <li key={item} className="border-b border-rule py-6 font-display text-xl leading-snug text-ink md:text-2xl">
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Close: one action back to the tools, and whether the compute service is up. */}
      <section aria-label={t.home.hero.tryTool} className="py-20 md:py-28">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-10 gap-y-6 px-4 md:px-6">
          <a href="#tools" className="btn btn-primary btn-lg">
            {t.home.hero.tryTool}
          </a>
          <ComputeStatus />
        </div>
      </section>
    </main>
  );
}
