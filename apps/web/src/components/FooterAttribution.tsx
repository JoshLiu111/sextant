"use client";

import { usePathname } from "next/navigation";
import { getMessages } from "@/i18n";
import { ATTRIBUTIONS, type Attribution, type AttributionId } from "@/lib/attributions";
import { toolForPath } from "@/lib/tools";
import { useCreditedSources } from "./PageSources";

/**
 * The footer's per-page attribution slot: the sources of the results on the
 * page plus those the page always uses (tool registry), in `ATTRIBUTIONS` order.
 */
export function FooterAttribution() {
  const t = getMessages();
  const always = toolForPath(usePathname())?.attributions ?? [];
  const credited = useCreditedSources();
  const ids = (Object.keys(ATTRIBUTIONS) as AttributionId[]).filter((id) => always.includes(id) || credited.has(id));

  return (
    <div data-testid="attribution-slot">
      {ids.length > 0 && (
        <ul aria-label={t.footer.sourcesLabel} className="flex flex-col gap-1">
          {ids.map((id) => {
            const a: Attribution = ATTRIBUTIONS[id];
            return (
              <li key={id} data-attribution={id}>
                {a.href ? (
                  <a href={a.href} className="underline" target="_blank" rel="noreferrer">
                    {a.text}
                  </a>
                ) : (
                  a.text
                )}
                {a.links?.map((link) => (
                  <span key={link.href}>
                    {" · "}
                    <a href={link.href} className="underline" target="_blank" rel="noreferrer">
                      {link.label}
                    </a>
                  </span>
                ))}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
