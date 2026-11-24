"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { SignInLink } from "@/components/SignInLink";
import { getMessages } from "@/i18n";
import { fetchAiQuota } from "@/lib/ai";
import type { HowToUse } from "@/lib/howToUse";
import { getTool, type ToolSlug } from "@/lib/tools";
import { hrefWithQuery } from "@/lib/urlInputs";

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
 * Open or collapsed for this tool. Open on the server and before hydration, so
 * the steps show without JavaScript; then the state remembered in this browser.
 * The button and the panel each read it, so they stay in step wherever they sit.
 */
function useOpen(tool: ToolSlug): boolean {
  return useSyncExternalStore(
    subscribe,
    () => readOpen(tool),
    () => true,
  );
}

const buttonId = (tool: ToolSlug) => `how-to-use-${tool}`;
const panelId = (tool: ToolSlug) => `how-to-use-panel-${tool}`;

/**
 * The "How to use" button for a tool page's title row (see `ToolPageHeader`):
 * a disclosure that opens and closes `HowToUsePanel` and remembers the choice.
 */
export function HowToUseButton({ tool }: { tool: ToolSlug }) {
  const copy = getMessages().common.howToUse;
  const open = useOpen(tool);
  return (
    <button
      type="button"
      id={buttonId(tool)}
      aria-expanded={open}
      aria-controls={panelId(tool)}
      onClick={() => storeOpen(tool, !open)}
      className="btn shrink-0"
    >
      {copy.heading}
    </button>
  );
}

/**
 * The "How to use" panel under a tool page's title: steps, "Try this" example
 * links, and for visitors what signing in adds on this tool. Content comes from
 * `tools[tool].howTo` in src/i18n. `HowToUseButton` opens and closes it; it is
 * open on a first visit. Collapsed, it stays in the page but hidden.
 */
export function HowToUsePanel({ tool }: { tool: ToolSlug }) {
  const t = getMessages();
  const copy = t.common.howToUse;
  // Every tool has `howTo`; the annotation makes a missing one a type error.
  const howTo: HowToUse = t.tools[tool].howTo;
  const open = useOpen(tool);
  const signedOut = useSignedOut();

  const href = getTool(tool).href;

  return (
    <section
      id={panelId(tool)}
      aria-labelledby={buttonId(tool)}
      hidden={!open}
      className="well mt-5"
    >
      <div className="space-y-3 p-4 text-sm md:px-5">
        <ol aria-label={copy.stepsLabel} className="max-w-[75ch] list-decimal space-y-1 pl-5 text-ink-2 marker:text-muted">
          {howTo.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        {howTo.examples.length > 0 && (
          <ul aria-label={copy.examplesLabel} className="flex flex-wrap gap-x-4 gap-y-1">
            {howTo.examples.map((example) => (
              <li key={example.label}>
                {/* A full navigation (not <Link>): the tool reads its URL inputs on load. */}
                <a href={hrefWithQuery(href, example.params)} className="link">
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
            <SignInLink className="link font-medium" />
          </div>
        )}
      </div>
    </section>
  );
}
