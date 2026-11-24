"use client";

import { useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useUrlInputs, type UrlCodec } from "@/lib/urlInputs";

/**
 * The open tab of a tool page, kept in the query string (`?tab=strategy`) so a
 * shared link opens the same tab. Writing the tab keeps every other param, so a
 * tool's own inputs and its tab share the URL. An unknown or missing tab opens
 * the first one. Uses `useSearchParams` (via `useUrlInputs`), so render the
 * caller inside `<Suspense>`.
 *
 * `ids` should be a module-level constant (`const TABS = ["overview", "checks"] as const`).
 */
export function useUrlTab<const Id extends string>(
  ids: readonly [Id, ...Id[]],
  param = "tab",
): [Id, (id: Id) => void] {
  const codec = useMemo<UrlCodec<{ tab: Id }>>(
    () => ({
      keys: [param],
      read: (params) => {
        const raw = params.get(param);
        return { tab: ids.find((id) => id === raw) ?? ids[0] };
      },
      write: ({ tab }) => ({ [param]: tab }),
    }),
    [ids, param],
  );
  const { initial, share } = useUrlInputs(codec);
  const [tab, setTabState] = useState<Id>(initial.tab);
  const setTab = (id: Id) => {
    setTabState(id);
    share({ tab: id });
  };
  return [tab, setTab];
}

export type TabItem<Id extends string> = { id: Id; label: string };

/**
 * An accessible tablist with one panel: the open tab's. Only the open panel is
 * mounted, so only it fetches. Arrow keys, Home and End move between tabs (and
 * open them); only the open tab is in the Tab order.
 *
 * Element ids are `${idPrefix}-tab-${id}` and `${idPrefix}-panel-${id}`.
 * Pair with `useUrlTab` for URL-backed state:
 *
 *   const [tab, setTab] = useUrlTab(TAB_IDS);
 *   <Tabs idPrefix="risk" label="Risk results" tabs={items} active={tab} onChange={setTab}>
 *     {tab === "overview" && <Overview />}
 *   </Tabs>
 */
export function Tabs<Id extends string>({
  idPrefix,
  label,
  tabs,
  active,
  onChange,
  children,
  className = "mt-6",
}: {
  idPrefix: string;
  /** The tablist's accessible name. */
  label: string;
  tabs: readonly TabItem<Id>[];
  active: Id;
  onChange: (id: Id) => void;
  /** The open tab's content. */
  children: ReactNode;
  className?: string;
}) {
  const buttons = useRef(new Map<Id, HTMLButtonElement>());

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const index = tabs.findIndex((t) => t.id === active);
    const next =
      e.key === "ArrowRight"
        ? (index + 1) % tabs.length
        : e.key === "ArrowLeft"
          ? (index - 1 + tabs.length) % tabs.length
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? tabs.length - 1
              : null;
    if (next === null) return;
    e.preventDefault();
    const id = tabs[next].id;
    onChange(id);
    buttons.current.get(id)?.focus();
  }

  return (
    <div className={className}>
      <div
        role="tablist"
        aria-label={label}
        onKeyDown={onKeyDown}
        className="flex flex-wrap gap-1 border-b border-black/10 dark:border-white/15"
      >
        {tabs.map(({ id, label: tabLabel }) => (
          <button
            key={id}
            ref={(el) => {
              if (el) buttons.current.set(id, el);
              else buttons.current.delete(id);
            }}
            id={`${idPrefix}-tab-${id}`}
            role="tab"
            type="button"
            aria-selected={active === id}
            aria-controls={`${idPrefix}-panel-${id}`}
            tabIndex={active === id ? 0 : -1}
            onClick={() => onChange(id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              active === id
                ? "border-black dark:border-white"
                : "border-transparent text-black/60 hover:text-black dark:text-white/60 dark:hover:text-white"
            }`}
          >
            {tabLabel}
          </button>
        ))}
      </div>
      <div id={`${idPrefix}-panel-${active}`} role="tabpanel" aria-labelledby={`${idPrefix}-tab-${active}`}>
        {children}
      </div>
    </div>
  );
}
