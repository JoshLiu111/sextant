"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { startTransition, useOptimistic } from "react";
import { getMessages } from "@/i18n";

export type Frequency = "annual" | "quarterly";
const FREQUENCIES: Frequency[] = ["annual", "quarterly"];

/** The page's period frequency: `?frequency=quarterly`, else annual. */
export function useFrequency(): Frequency {
  return useSearchParams().get("frequency") === "quarterly" ? "quarterly" : "annual";
}

/** Annual / quarterly switch for the whole page (ratios and statements), kept in the
 * URL as `?frequency=quarterly` alongside the forms' own params. */
export function FrequencyToggle() {
  const c = getMessages().company.frequency;
  // The URL updates asynchronously; show the choice at once.
  const [frequency, setFrequency] = useOptimistic(useFrequency());
  const router = useRouter();
  const pathname = usePathname();

  function choose(next: Frequency) {
    // The forms write their inputs straight to the address bar (lib/urlInputs), so start from it.
    const query = new URLSearchParams(window.location.search);
    if (next === "annual") query.delete("frequency");
    else query.set("frequency", next);
    const qs = query.toString();
    startTransition(() => {
      setFrequency(next);
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  }

  return (
    <fieldset className="mt-6">
      <legend className="text-sm font-medium">{c.legend}</legend>
      <div className="mt-1 inline-flex divide-x divide-muted overflow-hidden rounded-card border border-muted">
        {FREQUENCIES.map((f) => (
          <label
            key={f}
            className={`relative inline-flex min-h-9 cursor-pointer items-center whitespace-nowrap px-4 text-sm has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:-outline-offset-2 has-[:focus-visible]:outline-focus ${
              frequency === f ? "bg-ink text-paper" : "bg-paper-hi text-ink-2 hover:bg-paper-2 active:bg-paper-3"
            }`}
          >
            <input
              type="radio"
              name="frequency"
              value={f}
              checked={frequency === f}
              onChange={() => choose(f)}
              className="absolute inset-0 cursor-pointer appearance-none opacity-0"
            />
            {c[f]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
