"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ErrorNotice, FieldError, fieldErrorId } from "@/components/ErrorNotice";
import { getMessages } from "@/i18n";
import {
  portfoliosApi,
  type PortfolioBody,
  type PortfolioSummary,
  type SavedPortfolio,
} from "@/lib/portfolios";
import { SavedPortfolioResults } from "./SavedPortfolioResults";

// Inputs are kept as strings; `toBody` converts them to the API's numbers.
type HoldingRow = { ticker: string; quantity: string; cost_price: string; currency: string };
type Editor = { name: string; holdings: HoldingRow[] };

const EMPTY_ROW: HoldingRow = { ticker: "", quantity: "", cost_price: "", currency: "USD" };
const DRAFT: Editor = { name: "", holdings: [{ ...EMPTY_ROW }] };
const FIELDS = ["ticker", "quantity", "cost_price", "currency"] as const;

function numberOrNull(raw: string): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function toBody(editor: Editor): PortfolioBody {
  return {
    name: editor.name,
    holdings: editor.holdings.map((h) => ({
      ticker: h.ticker.trim(),
      quantity: numberOrNull(h.quantity),
      cost_price: numberOrNull(h.cost_price),
      currency: h.currency.trim(),
    })),
  };
}

function toEditor(p: SavedPortfolio): Editor {
  return {
    name: p.name,
    holdings: p.holdings.map((h) => ({
      ticker: h.ticker,
      quantity: String(h.quantity),
      cost_price: String(h.cost_price),
      currency: h.currency,
    })),
  };
}

const summaryOf = ({ id, name, created_at, updated_at }: SavedPortfolio): PortfolioSummary => ({
  id,
  name,
  created_at,
  updated_at,
});

const inputClass = (error: string | undefined) =>
  `w-full min-w-0 rounded-md border px-2 py-2 font-mono dark:bg-white/5 ${
    error ? "border-red-500" : "border-black/20 dark:border-white/20"
  }`;

const buttonClass =
  "rounded-md border border-black/20 px-3 py-1 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10";

/**
 * Create, rename, edit, delete and switch between the signed-in user's saved
 * portfolios. The selected portfolio's saved version drives the results below it.
 */
export function SavedPortfolios({ initial }: { initial: PortfolioSummary[] | null }) {
  const t = getMessages();
  const s = t.portfolio.saved;
  const [list, setList] = useState<PortfolioSummary[]>(initial ?? []);
  const [selectedId, setSelectedId] = useState<string | null>(initial?.[0]?.id ?? null);
  const [loaded, setLoaded] = useState<SavedPortfolio | null>(null);
  const [editor, setEditor] = useState<Editor>(DRAFT);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const loadedId = useRef<string | null>(null);

  // The server could not list the portfolios: try again from the browser.
  useEffect(() => {
    if (initial !== null) return;
    portfoliosApi.list().then((outcome) => {
      if (outcome.kind !== "ok") return setError(outcome.message);
      setList(outcome.value);
      setSelectedId((id) => id ?? outcome.value[0]?.id ?? null);
    });
  }, [initial]);

  // Load the selected portfolio into the editor (unless we already hold it, e.g. just saved).
  useEffect(() => {
    if (selectedId === null || loadedId.current === selectedId) return;
    let cancelled = false;
    portfoliosApi.get(selectedId).then((outcome) => {
      if (cancelled) return;
      if (outcome.kind !== "ok") return setError(outcome.message);
      show(outcome.value);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  function show(portfolio: SavedPortfolio | null) {
    loadedId.current = portfolio?.id ?? null;
    setLoaded(portfolio);
    setEditor(portfolio ? toEditor(portfolio) : { name: "", holdings: [{ ...EMPTY_ROW }] });
    setFieldErrors({});
    setError(null);
    setConfirmingDelete(false);
  }

  function select(id: string | null) {
    setNotice(null);
    if (id === null) show(null);
    setSelectedId(id);
  }

  const setHoldings = (update: (rows: HoldingRow[]) => HoldingRow[]) =>
    setEditor((e) => ({ ...e, holdings: update(e.holdings) }));
  const setCell = (index: number, field: keyof HoldingRow) => (value: string) =>
    setHoldings((rows) => rows.map((r, i) => (i === index ? { ...r, [field]: value } : r)));

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    const body = toBody(editor);
    const outcome = selectedId === null ? await portfoliosApi.create(body) : await portfoliosApi.update(selectedId, body);
    setBusy(false);
    if (outcome.kind === "invalid") {
      setFieldErrors(outcome.fields);
      setError(outcome.message);
      return;
    }
    if (outcome.kind === "failed") {
      setFieldErrors({});
      setError(outcome.message);
      return;
    }
    const saved = outcome.value;
    setList((l) =>
      l.some((p) => p.id === saved.id) ? l.map((p) => (p.id === saved.id ? summaryOf(saved) : p)) : [...l, summaryOf(saved)],
    );
    show(saved);
    setSelectedId(saved.id);
    setNotice(s.saved);
  }

  async function onDelete() {
    if (selectedId === null) return;
    setBusy(true);
    const outcome = await portfoliosApi.remove(selectedId);
    setBusy(false);
    if (outcome.kind !== "ok") return setError(outcome.message);
    const rest = list.filter((p) => p.id !== selectedId);
    setList(rest);
    select(rest[0]?.id ?? null);
  }

  const dirty = loaded !== null && JSON.stringify(toBody(editor)) !== JSON.stringify(toBody(toEditor(loaded)));
  const selectClass = "w-full min-w-0 rounded-md border border-black/20 px-3 py-2 dark:border-white/20 dark:bg-white/5";

  return (
    <section aria-labelledby="saved-portfolios" className="mt-8 rounded-lg border border-black/10 p-4 dark:border-white/15">
      <h2 id="saved-portfolios" className="text-xl font-semibold">
        {s.heading}
      </h2>
      <p className="mt-1 text-sm text-black/70 dark:text-white/70">{s.intro}</p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        {list.length > 0 ? (
          <div className="min-w-0 flex-1">
            <label htmlFor="saved-portfolio-switcher" className="block text-sm font-medium">
              {s.switcher}
            </label>
            <select
              id="saved-portfolio-switcher"
              value={selectedId ?? ""}
              onChange={(e) => select(e.target.value || null)}
              className={`mt-1 ${selectClass}`}
            >
              {selectedId === null && <option value="">{s.draft}</option>}
              {list.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <p className="min-w-0 flex-1 text-sm">{s.empty}</p>
        )}
        <button type="button" onClick={() => select(null)} className={buttonClass}>
          {s.newPortfolio}
        </button>
      </div>

      <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <form onSubmit={onSave} noValidate className="min-w-0 space-y-4">
          <div className="min-w-0">
            <label htmlFor="saved-portfolio-name" className="block text-sm font-medium">
              {s.name.label}
            </label>
            <input
              id="saved-portfolio-name"
              name="name"
              value={editor.name}
              placeholder={s.name.placeholder}
              onChange={(e) => setEditor((ed) => ({ ...ed, name: e.target.value }))}
              aria-invalid={fieldErrors.name ? true : undefined}
              aria-describedby={fieldErrors.name ? fieldErrorId("name") : undefined}
              className={`mt-1 ${inputClass(fieldErrors.name)} font-sans`}
            />
            <FieldError name="name" message={fieldErrors.name} />
          </div>

          <fieldset className="min-w-0" aria-describedby={fieldErrors.holdings ? fieldErrorId("holdings") : undefined}>
            <legend className="text-sm font-medium">{s.holdings.heading}</legend>
            <p className="mt-1 text-xs text-black/50 dark:text-white/50">{s.holdings.hint}</p>
            <div
              aria-hidden
              className="mt-2 grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,0.8fr)_2rem] gap-2 text-xs text-black/60 dark:text-white/60"
            >
              {FIELDS.map((f) => (
                <span key={f} className="truncate">
                  {s.holdings[f]}
                </span>
              ))}
            </div>
            <ol className="mt-1 space-y-2">
              {editor.holdings.map((row, i) => {
                const n = i + 1;
                const errors = FIELDS.map((f) => [`holdings.${i}.${f}`, fieldErrors[`holdings.${i}.${f}`]] as const);
                return (
                  <li key={i} className="min-w-0">
                    <div className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,0.8fr)_2rem] items-center gap-2">
                      {FIELDS.map((f, j) => {
                        const [name, message] = errors[j];
                        return (
                          <input
                            key={f}
                            name={name}
                            aria-label={`${s.holdings[f]} ${n}`}
                            inputMode={f === "quantity" || f === "cost_price" ? "decimal" : undefined}
                            autoCapitalize={f === "ticker" || f === "currency" ? "characters" : undefined}
                            spellCheck={false}
                            value={row[f]}
                            onChange={(e) => setCell(i, f)(e.target.value)}
                            aria-invalid={message ? true : undefined}
                            aria-describedby={message ? fieldErrorId(name) : undefined}
                            className={inputClass(message)}
                          />
                        );
                      })}
                      <button
                        type="button"
                        aria-label={`${s.holdings.remove} ${n}`}
                        disabled={editor.holdings.length === 1}
                        onClick={() => setHoldings((rows) => rows.filter((_, j) => j !== i))}
                        className="rounded-md px-2 py-1 text-lg leading-none text-black/60 hover:bg-black/5 disabled:opacity-30 dark:text-white/60 dark:hover:bg-white/10"
                      >
                        ×
                      </button>
                    </div>
                    {errors.map(([name, message]) => (
                      <FieldError key={name} name={name} message={message} />
                    ))}
                  </li>
                );
              })}
            </ol>
            <button
              type="button"
              onClick={() => setHoldings((rows) => [...rows, { ...EMPTY_ROW }])}
              className={`mt-2 ${buttonClass}`}
            >
              {s.holdings.add}
            </button>
            <FieldError name="holdings" message={fieldErrors.holdings} />
          </fieldset>

          {error && (
            <ErrorNotice
              title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
              message={error}
            />
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 disabled:opacity-60 dark:bg-white dark:text-black dark:hover:bg-white/80"
            >
              {busy ? s.saving : s.save}
            </button>
            <p role="status" className="text-sm text-green-700 dark:text-green-400">
              {notice}
            </p>
          </div>
          {dirty && <p className="text-xs text-black/60 dark:text-white/60">{s.unsavedNote}</p>}

          {selectedId !== null &&
            (confirmingDelete ? (
              <div className="flex flex-wrap items-center gap-3 rounded-md border border-red-300 p-3 dark:border-red-800">
                <p role="alert" className="w-full text-sm font-medium text-red-700 dark:text-red-400">
                  {s.delete.warning}
                </p>
                <button
                  type="button"
                  disabled={busy}
                  onClick={onDelete}
                  className="rounded bg-red-700 px-3 py-1.5 text-sm font-medium text-white"
                >
                  {s.delete.confirm}
                </button>
                <button type="button" onClick={() => setConfirmingDelete(false)} className={buttonClass}>
                  {s.delete.cancel}
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmingDelete(true)}
                className="rounded border border-red-700 px-3 py-1 text-sm font-medium text-red-700 dark:text-red-400"
              >
                {s.delete.button}
              </button>
            ))}
        </form>

        <div className="min-w-0">
          {loaded ? (
            <SavedPortfolioResults key={`${loaded.id}:${loaded.updated_at}`} portfolio={loaded} />
          ) : (
            selectedId !== null && <p className="text-sm text-black/60 dark:text-white/60">{s.loading}</p>
          )}
        </div>
      </div>
    </section>
  );
}
