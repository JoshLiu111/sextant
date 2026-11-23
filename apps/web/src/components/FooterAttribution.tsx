"use client";

import { usePathname } from "next/navigation";
import { getMessages } from "@/i18n";
import { ATTRIBUTIONS, type Attribution } from "@/lib/attributions";
import { toolForPath } from "@/lib/tools";

/** The footer's per-page attribution slot, filled from the tool registry. */
export function FooterAttribution() {
  const t = getMessages();
  const ids = toolForPath(usePathname())?.attributions ?? [];

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
