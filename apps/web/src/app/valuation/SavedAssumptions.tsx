"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { SignInLink } from "@/components/SignInLink";
import { TextField } from "@/components/TextField";
import { getMessages } from "@/i18n";
import {
  valuationAssumptionsApi,
  type AssumptionSet,
  type AssumptionSetBody,
  type ValuationAssumptions,
} from "@/lib/valuationAssumptions";

/**
 * Save the current assumptions under a name for this ticker, and load or delete
 * earlier sets (story 70). Visitors get a sign-in prompt instead. Saving under a
 * name that already exists for the ticker replaces that set.
 */
export function SavedAssumptions({
  ticker,
  current,
  onLoad,
}: {
  /** The ticker being valued (the submitted one). */
  ticker: string;
  /** The form's assumptions as the API wants them. */
  current: () => AssumptionSetBody["assumptions"];
  onLoad: (assumptions: ValuationAssumptions) => void;
}) {
  const v = getMessages().valuation.saved;
  const [sets, setSets] = useState<AssumptionSet[] | "signed_out" | null>(null);
  const [name, setName] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const refresh = useCallback(async () => {
    const outcome = await valuationAssumptionsApi.list(ticker);
    if (outcome.kind === "ok") setSets(outcome.value);
    else if (outcome.kind === "signed_out") setSets("signed_out");
    else setError(outcome.message);
  }, [ticker]);

  useEffect(() => {
    let live = true;
    valuationAssumptionsApi.list(ticker).then((outcome) => {
      if (!live) return;
      if (outcome.kind === "ok") setSets(outcome.value);
      else if (outcome.kind === "signed_out") setSets("signed_out");
      else setError(outcome.message);
    });
    return () => {
      live = false;
    };
  }, [ticker]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setStatus(null);
    setError(null);
    const outcome = await valuationAssumptionsApi.save({
      ticker,
      name,
      assumptions: current(),
    });
    if (outcome.kind === "ok") {
      setFieldErrors({});
      setStatus(v.savedAs(outcome.value.name));
      await refresh();
    } else if (outcome.kind === "signed_out") setSets("signed_out");
    else {
      setFieldErrors(outcome.kind === "invalid" ? outcome.fields : {});
      setError(outcome.kind === "invalid" ? v.invalid : outcome.message);
    }
  }

  function onLoadSet(set: AssumptionSet) {
    onLoad(set.assumptions);
    setError(null);
    setStatus(v.loaded(set.name));
  }

  async function onDelete(set: AssumptionSet) {
    setStatus(null);
    const outcome = await valuationAssumptionsApi.remove(set.id);
    if (outcome.kind === "ok") {
      setStatus(v.deleted(set.name));
      await refresh();
    } else if (outcome.kind !== "signed_out") setError(outcome.message);
  }

  return (
    <section
      data-testid="saved-assumptions"
      aria-labelledby="saved-assumptions-heading"
      className="space-y-3"
    >
      <h2 id="saved-assumptions-heading" className="text-lg font-semibold">
        {v.heading}
      </h2>
      {sets === null ? null : sets === "signed_out" ? (
        <p className="text-sm text-black/70 dark:text-white/70">
          {v.signInPrompt} <SignInLink className="font-medium underline" />
        </p>
      ) : (
        <>
          <p className="text-sm text-black/60 dark:text-white/60">
            {v.intro(ticker)}
          </p>
          <form
            onSubmit={onSave}
            noValidate
            className="space-y-2"
            aria-label={v.heading}
          >
            <TextField
              name="assumption-name"
              label={v.nameLabel}
              hint={v.nameHint}
              value={name}
              onChange={setName}
              error={fieldErrors.name}
            />
            <button
              type="submit"
              className="rounded-md border border-black/20 px-3 py-1.5 text-sm font-medium hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
            >
              {v.save}
            </button>
          </form>
          {status && (
            <p
              role="status"
              className="text-sm text-black/70 dark:text-white/70"
            >
              {status}
            </p>
          )}
          {error && (
            <ErrorNotice
              title={getMessages().common.errors.heading}
              message={error}
            />
          )}
          {sets.length === 0 ? (
            <p className="text-sm text-black/60 dark:text-white/60">
              {v.none(ticker)}
            </p>
          ) : (
            <ul
              aria-label={v.listLabel(ticker)}
              className="divide-y divide-black/10 rounded-md border border-black/10 dark:divide-white/10 dark:border-white/10"
            >
              {sets.map((set) => (
                <li
                  key={set.id}
                  className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
                >
                  <span className="min-w-0 truncate font-medium">
                    {set.name}
                  </span>
                  <span className="flex shrink-0 gap-2">
                    <button
                      type="button"
                      onClick={() => onLoadSet(set)}
                      aria-label={v.loadNamed(set.name)}
                      className="rounded border border-black/20 px-2 py-0.5 hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
                    >
                      {v.load}
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(set)}
                      aria-label={v.deleteNamed(set.name)}
                      className="rounded border border-black/20 px-2 py-0.5 text-red-700 hover:bg-red-50 dark:border-white/20 dark:text-red-400 dark:hover:bg-white/10"
                    >
                      {v.delete}
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
