import type { ReactNode } from "react";
import { ToolCard } from "@/components/ToolCard";
import { getMessages, type Messages } from "@/i18n";
import { TOOLS_BY_GROUP, type Tool } from "@/lib/tools";

/**
 * The tool cards in the registry's groups (lib/tools.ts), one labelled section
 * per group, the same groups the nav shows. Shared by the landing page and the
 * dashboard; `personal` fills a card's optional signed-in slot.
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
    <div className="flex flex-col gap-8">
      {TOOLS_BY_GROUP.map(({ group, tools }) => {
        const headingId = `tool-group-${group}`;
        return (
          <section key={group} aria-labelledby={headingId}>
            <h3 id={headingId} className="text-lg font-semibold tracking-tight">
              {t.toolGroups[group]}
            </h3>
            <ul className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {tools.map((tool) => (
                <li key={tool.slug}>
                  <ToolCard tool={tool} action={action} personal={personal?.(tool)} />
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
