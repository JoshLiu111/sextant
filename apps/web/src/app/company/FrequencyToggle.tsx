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

/** Annual / quarterly switch for the whole page (ratios and statements), kept in the URL. */
export function FrequencyToggle() {
  const c = getMessages().company.frequency;
  // The URL updates asynchronously; show the choice at once.
  const [frequency, setFrequency] = useOptimistic(useFrequency());
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  function choose(next: Frequency) {
    const query = new URLSearchParams(params.toString());
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
      <div className="mt-2 inline-flex rounded-md border border-black/20 p-0.5 dark:border-white/20">
        {FREQUENCIES.map((f) => (
          <label
            key={f}
            className={`relative cursor-pointer rounded px-3 py-1.5 text-sm has-[:focus-visible]:outline has-[:focus-visible]:outline-2 ${
              frequency === f ? "bg-black text-white dark:bg-white dark:text-black" : "hover:bg-black/5 dark:hover:bg-white/10"
            }`}
          >
            <input
              type="radio"
              name="frequency"
              value={f}
              checked={frequency === f}
              onChange={() => choose(f)}
              className="absolute inset-0 cursor-pointer appearance-none rounded opacity-0"
            />
            {c[f]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
