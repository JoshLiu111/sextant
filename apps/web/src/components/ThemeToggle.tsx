"use client";

import { useSyncExternalStore } from "react";
import { getMessages } from "@/i18n";

/** localStorage key for the visitor's explicit choice; absent means "follow the system". */
export const THEME_KEY = "theme";

/**
 * Runs in <head> before first paint (see layout.tsx): sets <html data-theme> from the
 * saved choice, else from the system, and keeps following the system while there is
 * no saved choice. Without scripting the page stays light.
 */
export const THEME_SCRIPT = `(function(){try{var d=document.documentElement,m=matchMedia("(prefers-color-scheme: dark)");function a(){var t=localStorage.getItem("${THEME_KEY}");d.dataset.theme=t==="dark"||t==="light"?t:m.matches?"dark":"light"}a();m.addEventListener("change",a)}catch(e){}})()`;

type Theme = "light" | "dark";

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}
const current = (): Theme | null => (document.documentElement.dataset.theme === "dark" ? "dark" : "light");
const onServer = () => null;

/** The nav's light/dark switch: one click flips the page and remembers the choice. */
export function ThemeToggle() {
  const t = getMessages().site;
  const theme = useSyncExternalStore(subscribe, current, onServer);
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      data-testid="theme-toggle"
      aria-label={next === "dark" ? t.toDark : t.toLight}
      title={next === "dark" ? t.toDark : t.toLight}
      className="theme-toggle"
      onClick={() => {
        document.documentElement.dataset.theme = next;
        try {
          localStorage.setItem(THEME_KEY, next);
        } catch {
          // Storage blocked: the switch still holds for this page.
        }
      }}
    >
      {/* The icon names the mode the click goes to: a moon in light, a sun in dark. */}
      {theme === "dark" ? (
        <svg aria-hidden viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
          <circle cx="8" cy="8" r="3" />
          <path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1" />
        </svg>
      ) : (
        <svg aria-hidden viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round">
          <path d="M13.5 9.6A5.6 5.6 0 0 1 6.4 2.5a5.6 5.6 0 1 0 7.1 7.1Z" />
        </svg>
      )}
    </button>
  );
}
