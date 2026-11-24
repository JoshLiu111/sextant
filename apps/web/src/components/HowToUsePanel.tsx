"use client";

import { useEffect, useState, useSyncExternalStore, type SyntheticEvent } from "react";
import { SignInLink } from "@/components/SignInLink";
import { getMessages } from "@/i18n";
import { fetchAiQuota } from "@/lib/ai";
import { exampleHref, type HowToUse } from "@/lib/howToUse";
import { getTool, type ToolSlug } from "@/lib/tools";

/** Open or collapsed, per tool, in this browser only (never sent to the server). */
const storageKey = (tool: ToolSlug) => `sextant:how-to-use:${tool}`;

const CHANGE_EVENT = "sextant:how-to-use";

function readOpen(tool: ToolSlug): boolean {
  try {
    return window.localStorage.getItem(storageKey(tool)) !== "closed";
  } catch {
    return true;
  }
}

function storeOpen(tool: ToolSlug, open: boolean) {
  try {
    window.localStorage.setItem(storageKey(tool), open ? "open" : "closed");
  } catch {
    // Storage blocked: the panel still toggles, it just isn't remembered.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/**
 * Whether the visitor is signed out, decided in the browser as AI Explain does
 * (the AI quota answers 401). Unknown while loading or if the check fails.
 */
function useSignedOut(): boolean {
  const [signedOut, setSignedOut] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetchAiQuota(controller.signal)
      .then((outcome) => setSignedOut(outcome.kind === "signed_out"))
      .catch(() => {});
    return () => controller.abort();
  }, []);
  return signedOut;
}

/**
 * The collapsible "How to use" panel at the top of a tool page: steps, "Try
 * this" example links, and for visitors what signing in adds on this tool.
 * Content comes from `tools[tool].howTo` in src/i18n. Renders open before
 * hydration, then follows the state remembered for this tool.
 */
export function HowToUsePanel({ tool }: { tool: ToolSlug }) {
  const t = getMessages();
  const copy = t.common.howToUse;
  // Tools without `howTo` yet render nothing.
  const entry: { name: string; howTo?: HowToUse } = t.tools[tool];
  const howTo = entry.howTo;
  // Open on the server and before hydration, so the steps show without JavaScript.
  const open = useSyncExternalStore(
    subscribe,
    () => readOpen(tool),
    () => true,
  );
  const signedOut = useSignedOut();

  if (!howTo) return null;
  const href = getTool(tool).href;
  const headingId = `how-to-use-${tool}`;

  // A native <details> fires `toggle` for any change, including ones React made
  // (and the open-on-load one); only a change away from the stored state is the visitor's.
  function onToggle(e: SyntheticEvent<HTMLDetailsElement>) {
    const next = e.currentTarget.open;
    if (next !== open) storeOpen(tool, next);
  }

  return (
    <section aria-labelledby={headingId} className="mt-4 rounded-lg border border-black/10 dark:border-white/15">
      <details open={open} onToggle={onToggle}>
        <summary id={headingId} className="cursor-pointer px-4 py-2 font-medium">
          {copy.heading}
        </summary>
        <div className="space-y-3 px-4 pb-4 text-sm">
          <ol aria-label={copy.stepsLabel} className="list-decimal space-y-1 pl-5 text-black/80 dark:text-white/80">
            {howTo.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          {howTo.examples.length > 0 && (
            <ul aria-label={copy.examplesLabel} className="flex flex-wrap gap-x-4 gap-y-1">
              {howTo.examples.map((example) => (
                <li key={example.label}>
                  {/* A full navigation (not <Link>): the tool reads its URL inputs on load. */}
                  <a href={exampleHref(href, example.params)} className="underline underline-offset-2 hover:no-underline">
                    {copy.tryThis} {example.label}
                  </a>
                </li>
              ))}
            </ul>
          )}
          {signedOut && howTo.signedInExtras.length > 0 && (
            <div data-testid="signed-in-extras" className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <p>
                {copy.signedInExtras} {howTo.signedInExtras.join("; ")}.
              </p>
              <SignInLink className="font-medium underline underline-offset-2 hover:no-underline" />
            </div>
          )}
        </div>
      </details>
    </section>
  );
}
