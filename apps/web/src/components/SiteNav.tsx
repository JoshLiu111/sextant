"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { getMessages } from "@/i18n";
import { TOOLS_BY_GROUP, type ToolGroup } from "@/lib/tools";

/**
 * The top bar. Tools come in the registry's groups (lib/tools.ts): a group with
 * several tools is a disclosure menu, a one-tool group is a direct link. One menu
 * is open at a time; Escape, a click outside or following a link closes it.
 * `account` and `logo` are server-rendered from the signed-in state (see AccountMenu and NavLogo).
 */
export function SiteNav({ account, logo }: { account?: ReactNode; logo: ReactNode }) {
  const t = getMessages();
  const [open, setOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<ToolGroup | null>(null);
  const navRef = useRef<HTMLElement>(null);
  const buttons = useRef<Partial<Record<ToolGroup, HTMLButtonElement | null>>>({});

  useEffect(() => {
    if (!openGroup) return;
    function onPointerDown(event: PointerEvent) {
      if (!navRef.current?.contains(event.target as Node)) setOpenGroup(null);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || !openGroup) return;
      setOpenGroup(null);
      buttons.current[openGroup]?.focus();
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openGroup]);

  function closeAll() {
    setOpenGroup(null);
    setOpen(false);
  }

  return (
    <header className="proof px-3 pt-3 md:px-6 md:pt-4">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-2 rounded-card border border-rule bg-paper-hi px-4 py-2 shadow-sheet md:px-5">
        {logo}
        <div className="ml-auto md:order-last">{account}</div>
        <button
          type="button"
          className="btn btn-sm md:hidden"
          aria-expanded={open}
          aria-controls="tools-nav"
          onClick={() => setOpen((o) => !o)}
        >
          {t.site.menu}
        </button>
        <nav
          id="tools-nav"
          ref={navRef}
          aria-label={t.site.toolsNavLabel}
          className={`${open ? "block" : "hidden"} w-full md:block md:w-auto`}
        >
          <ul className="flex flex-col gap-1 py-2 md:flex-row md:flex-wrap md:gap-1 md:py-0">
            {TOOLS_BY_GROUP.map(({ group, tools }) => {
              if (tools.length === 1) {
                const [tool] = tools;
                return (
                  <li key={group}>
                    <Link href={tool.href} className={NAV_ITEM} onClick={closeAll}>
                      {t.tools[tool.slug].name}
                    </Link>
                  </li>
                );
              }
              const expanded = openGroup === group;
              const menuId = `nav-group-${group}`;
              return (
                <li key={group} className="md:relative">
                  <button
                    type="button"
                    ref={(el) => {
                      buttons.current[group] = el;
                    }}
                    className={`${NAV_ITEM} inline-flex items-center gap-1.5 aria-expanded:bg-paper-2`}
                    aria-expanded={expanded}
                    aria-controls={menuId}
                    onClick={() => setOpenGroup(expanded ? null : group)}
                  >
                    {t.toolGroups[group]}
                    <svg aria-hidden width="9" height="6" viewBox="0 0 9 6" className="text-muted">
                      <path d="M1 1l3.5 3.5L8 1" fill="none" stroke="currentColor" strokeWidth="1.25" />
                    </svg>
                  </button>
                  <ul
                    id={menuId}
                    className={`${expanded ? "flex" : "hidden"} flex-col gap-0.5 pb-1 pl-4 md:absolute md:left-0 md:top-full md:z-[var(--z-dropdown)] md:mt-2 md:min-w-max md:rounded-card md:border md:border-rule md:bg-paper-hi md:p-1.5 md:shadow-sheet`}
                  >
                    {tools.map((tool) => (
                      <li key={tool.slug}>
                        <Link href={tool.href} className={NAV_ITEM} onClick={closeAll}>
                          {t.tools[tool.slug].name}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </header>
  );
}

/** One nav link or group button: body face, one weight, state as a soft background. */
const NAV_ITEM =
  "block whitespace-nowrap rounded-card px-3 py-2 text-sm text-ink-2 transition-colors duration-[var(--dur-short)] hover:bg-paper-2 hover:text-ink active:bg-paper-3";
