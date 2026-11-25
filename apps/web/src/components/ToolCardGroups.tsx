import Image from "next/image";
import type { ReactNode } from "react";
import { ToolCard } from "@/components/ToolCard";
import { getMessages, type Messages } from "@/i18n";
import { TOOLS_BY_GROUP, type Tool, type ToolGroup, type ToolSlug } from "@/lib/tools";

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

/**
 * Every tool on one grid, grouped as the nav groups them (lib/tools.ts), each card
 * with its illustration; the whole card opens the tool and the action shows over
 * the picture on hover or focus. Shared by the landing page (`action="openDemo"`)
 * and the dashboard (`action="open"`); `personal` fills a card's signed-in slot.
 */
export function ToolCardGroups({
  action,
  personal,
}: {
  action: keyof Messages["common"]["toolCard"];
  personal?: (tool: Tool) => ReactNode;
}) {
  const t = getMessages();
  return (
    <div className="grid grid-cols-1 gap-x-6 gap-y-12 md:grid-cols-2 lg:grid-cols-4">
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
                      action={action}
                      personal={personal?.(tool)}
                      revealAction
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
  );
}
