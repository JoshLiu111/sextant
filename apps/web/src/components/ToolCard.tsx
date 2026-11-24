import Link from "next/link";
import type { ReactNode } from "react";
import { getMessages, type Messages } from "@/i18n";
import type { Tool } from "@/lib/tools";

/**
 * One tool as a card: the question it answers, its highlights and a link that
 * opens it. Shared by the landing page (`action="openDemo"`) and the dashboard
 * (`action="open"`); `personal` is an optional slot for the signed-in user's
 * own info about this tool.
 */
export function ToolCard({
  tool,
  action,
  personal,
  wide = false,
  picture,
}: {
  tool: Tool;
  action: keyof Messages["common"]["toolCard"];
  personal?: ReactNode;
  /** Lay the card out across a wide row: the question beside the highlights. */
  wide?: boolean;
  /** An illustration set at the top of the card (the landing page's). */
  picture?: ReactNode;
}) {
  const t = getMessages();
  const label = t.common.toolCard[action];
  const copy = t.tools[tool.slug];
  const headingId = `tool-card-${tool.slug}`;
  return (
    <article
      aria-labelledby={headingId}
      data-testid="tool-card"
      data-tool={tool.slug}
      className={`card flex h-full flex-col p-5 md:p-6 ${wide ? "md:grid md:grid-cols-[minmax(0,6fr)_minmax(0,5fr)] md:gap-x-10" : ""}`}
    >
      {picture && <div className="-mx-1 -mt-1 mb-5 md:col-span-2">{picture}</div>}
      <div className="min-w-0">
        <span aria-hidden className="tool-rule mb-4" />
        <h4 id={headingId} className="text-sm font-medium text-ink-2">
          {copy.name}
        </h4>
        {/* The question leads: it is what the visitor came to ask. */}
        <p data-testid="tool-question" className={`mt-2 font-display leading-snug text-ink ${picture ? "text-xl" : "text-xl md:text-2xl"}`}>
          {copy.question}
        </p>
      </div>
      <div className="flex min-w-0 grow flex-col">
        <ul className={`mt-4 flex list-disc flex-col gap-1 pl-5 text-sm text-ink-2 marker:text-muted ${wide ? "md:mt-9" : ""}`}>
          {copy.highlights.map((highlight) => (
            <li key={highlight}>{highlight}</li>
          ))}
        </ul>
        {personal && <div className="mt-3 text-sm">{personal}</div>}
        {tool.status === "coming-soon" && (
          <span className="mt-3 self-start text-xs font-medium text-muted">{t.comingSoon.badge}</span>
        )}
        {/* The link is the button, so its focus ring sits on the button. */}
        <div className="mt-auto pt-5">
          <Link href={tool.href} aria-label={`${label}: ${copy.name}`} className="btn btn-tool btn-lg">
            {label}
          </Link>
        </div>
      </div>
    </article>
  );
}
