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
      <h2 id="saved-assumptions-heading" className="text-xl">
        {v.heading}
      </h2>
      {sets === null ? null : sets === "signed_out" ? (
        <p className="text-sm text-ink-2">
          {v.signInPrompt} <SignInLink className="link font-medium whitespace-nowrap focus-visible:outline-2 focus-visible:outline-focus" />
        </p>
      ) : (
        <>
          <p className="max-w-[65ch] text-sm text-muted">
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
              className="btn whitespace-nowrap"
            >
              {v.save}
            </button>
          </form>
          {status && (
            <p
              role="status"
              className="text-sm text-ink-2"
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
            <p className="text-sm text-muted">
              {v.none(ticker)}
            </p>
          ) : (
            <ul
              aria-label={v.listLabel(ticker)}
              className="divide-y divide-rule border-y border-rule"
            >
              {sets.map((set) => (
                <li
                  key={set.id}
                  className="flex items-center justify-between gap-2 py-2 text-sm"
                >
                  <span className="min-w-0 truncate font-medium">
                    {set.name}
                  </span>
                  <span className="flex shrink-0 gap-2">
                    <button
                      type="button"
                      onClick={() => onLoadSet(set)}
                      aria-label={v.loadNamed(set.name)}
                      className="btn btn-sm whitespace-nowrap"
                    >
                      {v.load}
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(set)}
                      aria-label={v.deleteNamed(set.name)}
                      className="btn btn-sm btn-danger whitespace-nowrap"
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
