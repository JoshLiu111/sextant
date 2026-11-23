"use client";

import { getMessages } from "@/i18n";
import { DEMO_SOURCE, PROVIDER_NAMES, type MyDataProvider, type PriceSource } from "@/lib/myData";

/**
 * "Demo data / My data" switch for market-data tools. Renders nothing unless the
 * visitor has a My data provider (`useMyDataProviders()`), so visitors and users
 * without a key stay on demo data. One "My data" option per provider; with
 * several keys (Tiingo and FMP) each option names its provider.
 */
export function DataModeToggle({
  providers,
  value,
  onChange,
}: {
  providers: readonly MyDataProvider[];
  value: PriceSource;
  onChange: (source: PriceSource) => void;
}) {
  if (providers.length === 0) return null;
  const t = getMessages().common.dataMode;
  const options: { source: PriceSource; label: string }[] = [
    { source: DEMO_SOURCE, label: t.demo },
    ...providers.map((p) => ({
      source: p,
      label: providers.length > 1 ? t.myDataFrom(PROVIDER_NAMES[p]) : t.myData,
    })),
  ];
  return (
    <fieldset data-testid="data-mode" className="min-w-0">
      <legend className="text-sm font-medium">{t.legend}</legend>
      <div className="mt-1 inline-flex rounded-md border border-black/20 p-0.5 dark:border-white/20">
        {options.map((o) => (
          <label
            key={o.source}
            className="cursor-pointer rounded px-3 py-1 text-sm has-[:checked]:bg-black has-[:checked]:text-white has-[:focus-visible]:ring-2 dark:has-[:checked]:bg-white dark:has-[:checked]:text-black"
          >
            <input
              type="radio"
              name="data-mode"
              value={o.source}
              checked={value === o.source}
              onChange={() => onChange(o.source)}
              className="sr-only"
            />
            {o.label}
          </label>
        ))}
      </div>
      {value !== DEMO_SOURCE && (
        <p data-testid="my-data-note" className="mt-1 text-xs text-black/60 dark:text-white/60">
          {t.note(PROVIDER_NAMES[value])}
        </p>
      )}
    </fieldset>
  );
}
