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
      <header data-testid="tool-title-row" className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <h1 className="text-2xl font-semibold">{title}</h1>
        <HowToUseButton tool={tool} />
      </header>
      <p className="mt-2 text-black/70 dark:text-white/70">{intro}</p>
      <HowToUsePanel tool={tool} />
    </>
  );
}
