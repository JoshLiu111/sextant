"use client";

import { FieldError } from "@/components/ErrorNotice";
import { NumberField } from "@/components/NumberField";
import { getMessages } from "@/i18n";

/** Return periods accepted by POST /risk/metrics (`period`). */
export const PERIODS = ["daily", "weekly", "monthly", "quarterly", "yearly"] as const;
export type ReturnPeriod = (typeof PERIODS)[number];

export const DEFAULT_ROLLING_WINDOW = "63";

/** Return period select and rolling window input for the Risk form. */
export function TimescaleInputs({
  period,
  rollingWindow,
  onPeriod,
  onRollingWindow,
  fieldErrors,
}: {
  period: ReturnPeriod;
  rollingWindow: string;
  onPeriod: (value: ReturnPeriod) => void;
  onRollingWindow: (value: string) => void;
  fieldErrors: Record<string, string>;
}) {
  const ts = getMessages().risk.timescale;
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-1">
      <div>
        <label htmlFor="input-period" className="block text-sm font-medium">
          {ts.inputs.period.label}
        </label>
        <select
          id="input-period"
          name="period"
          value={period}
          onChange={(e) => onPeriod(e.target.value as ReturnPeriod)}
          className="mt-1 w-full rounded-md border border-black/20 px-3 py-2 dark:border-white/20 dark:bg-white/5"
        >
          {PERIODS.map((p) => (
            <option key={p} value={p}>
              {ts.periods[p].label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-black/50 dark:text-white/50">{ts.inputs.period.hint}</p>
        <FieldError name="period" message={fieldErrors.period} />
      </div>
      <NumberField
        name="rolling_window"
        label={ts.inputs.rolling_window.label}
        hint={ts.inputs.rolling_window.hint}
        value={rollingWindow}
        onChange={onRollingWindow}
        error={fieldErrors.rolling_window}
        step="1"
      />
    </div>
  );
}

/** Which return period the statistics above use, and how they are annualized. */
export function PeriodNote({ period }: { period: ReturnPeriod | undefined }) {
  if (!period) return null;
  const ts = getMessages().risk.timescale;
  const p = ts.periods[period];
  return (
    <p data-testid="period-note" className="mt-1 text-sm text-black/70 dark:text-white/70">
      {ts.periodNote(p.label.toLowerCase(), p.perYear, p.noun)}
    </p>
  );
}
