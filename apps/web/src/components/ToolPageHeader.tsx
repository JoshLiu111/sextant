import { HowToUseButton, HowToUsePanel } from "@/components/HowToUsePanel";
import { getMessages } from "@/i18n";
import type { ToolSlug } from "@/lib/tools";

/**
 * The top of a tool page: a title row with the page heading (the tool's name)
 * and the "How to use" button, the intro line, then the (collapsible) "How to
 * use" panel.
 */
export function ToolPageHeader({ tool, intro }: { tool: ToolSlug; intro: string }) {
  const title = getMessages().tools[tool].name;
  return (
    <>
      <header data-testid="tool-title-row" className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <span aria-hidden className="tool-rule mb-4" />
          <h1 className="text-3xl leading-none text-ink">{title}</h1>
        </div>
        <HowToUseButton tool={tool} />
      </header>
      <p className="mt-3 max-w-[65ch] text-ink-2">{intro}</p>
      <HowToUsePanel tool={tool} />
    </>
  );
}
