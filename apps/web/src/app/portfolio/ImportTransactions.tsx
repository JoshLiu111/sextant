"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { ErrorNotice, FieldError, fieldErrorId } from "@/components/ErrorNotice";
import { getMessages } from "@/i18n";
import {
  IMPORT_FIELDS,
  REQUIRED_IMPORT_FIELDS,
  portfoliosApi,
  type ColumnMapping,
  type ImportField,
  type ImportPreview,
  type SavedPortfolio,
} from "@/lib/portfolios";

const buttonClass =
  "btn btn-sm";
const selectClass = "field mt-1 text-sm";
const cellClass = "border-b border-rule px-2 py-1 text-left tabular-nums text-xs whitespace-nowrap";

/**
 * Upload a CSV of transactions into the selected saved portfolio: preview the
 * first rows, match each field to a column, see the rows that will be skipped,
 * then import the rest in one go. Previews store nothing; the API does the parsing.
 */
export function ImportTransactions({
  portfolioId,
  onImported,
}: {
  portfolioId: string;
  onImported: (portfolio: SavedPortfolio) => void;
}) {
  const t = getMessages();
  const s = t.portfolio.saved.import;
  const [csv, setCsv] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const request = useRef(0);

  async function runPreview(text: string, mapping?: ColumnMapping) {
    const id = ++request.current;
    setBusy(true);
    const outcome = await portfoliosApi.previewImport(portfolioId, mapping ? { csv: text, mapping } : { csv: text });
    if (id !== request.current) return;
    setBusy(false);
    if (outcome.kind === "ok") {
      setPreview(outcome.value);
      setFieldErrors({});
      setError(null);
      return;
    }
    setFieldErrors(outcome.kind === "invalid" ? outcome.fields : {});
    setError(outcome.message);
    // A bad file has nothing to preview; a bad mapping keeps the last good preview.
    if (outcome.kind === "invalid" && "csv" in outcome.fields) setPreview(null);
  }

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    setNotice(null);
    if (!file) return reset();
    const text = await file.text();
    setCsv(text);
    setPreview(null);
    await runPreview(text);
  }

  function onMap(field: ImportField, column: string) {
    if (csv === null || preview === null) return;
    const mapping = { ...preview.mapping, [field]: column || null };
    setPreview({ ...preview, mapping });
    void runPreview(csv, mapping);
  }

  function reset() {
    request.current++;
    setCsv(null);
    setPreview(null);
    setFieldErrors({});
    setError(null);
    setBusy(false);
    if (fileInput.current) fileInput.current.value = "";
  }

  async function onImport() {
    if (csv === null || preview === null) return;
    setBusy(true);
    const outcome = await portfoliosApi.importTransactions(portfolioId, { csv, mapping: preview.mapping });
    setBusy(false);
    if (outcome.kind !== "ok") {
      setFieldErrors(outcome.kind === "invalid" ? outcome.fields : {});
      setError(outcome.message);
      return;
    }
    reset();
    setNotice(s.done(outcome.value.imported));
    onImported(outcome.value.portfolio);
  }

  const ready = preview !== null && preview.missing_fields.length === 0;
  const importable = ready ? preview.transactions.length : 0;

  return (
    <section aria-labelledby="import-transactions" className="mt-8 border-t border-rule pt-6">
      <h3 id="import-transactions" className="text-xl">
        {s.heading}
      </h3>
      <p className="mt-1 max-w-[55ch] text-sm text-ink-2">{s.intro}</p>

      <div className="mt-3">
        <label htmlFor="import-csv-file" className="label">
          {s.file}
        </label>
        <input
          ref={fileInput}
          id="import-csv-file"
          type="file"
          accept=".csv,text/csv,text/plain"
          onChange={onFile}
          aria-invalid={fieldErrors.csv ? true : undefined}
          aria-describedby={fieldErrors.csv ? fieldErrorId("csv") : undefined}
          className="mt-1 block w-full min-w-0 text-sm"
        />
        <FieldError name="csv" message={fieldErrors.csv} />
      </div>

      {notice && (
        <p role="status" className="mt-3 text-sm text-success">
          {notice}
        </p>
      )}

      {preview && (
        <div className="mt-4 space-y-5">
          <fieldset className="min-w-0">
            <legend className="label">{s.mappingHeading}</legend>
            <p className="hint mt-1">{s.mappingHint}</p>
            <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {IMPORT_FIELDS.map((field) => {
                const name = `mapping.${field}`;
                const message = fieldErrors[name];
                const required = REQUIRED_IMPORT_FIELDS.includes(field);
                const unmapped = required && preview.missing_fields.includes(field);
                return (
                  <div key={field} className="min-w-0">
                    <label htmlFor={`import-map-${field}`} className="block text-xs font-medium">
                      {`${s.columnFor} ${s.fields[field]}`}
                      <span className="ml-1 font-normal text-muted">
                        ({required ? s.required : s.optional})
                      </span>
                    </label>
                    <select
                      id={`import-map-${field}`}
                      aria-label={`${s.columnFor} ${s.fields[field]}`}
                      value={preview.mapping[field] ?? ""}
                      onChange={(e) => onMap(field, e.target.value)}
                      aria-invalid={message || unmapped ? true : undefined}
                      aria-describedby={message ? fieldErrorId(name) : undefined}
                      className={`${selectClass} ${message || unmapped ? "border-error" : ""}`}
                    >
                      <option value="">{s.notInFile}</option>
                      {preview.columns.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                    {!required && !preview.mapping[field] && (
                      <p className="mt-0.5 text-xs text-muted">
                        {s.defaults[field as "fees" | "currency"]}
                      </p>
                    )}
                    <FieldError name={name} message={message} />
                  </div>
                );
              })}
            </div>
          </fieldset>

          <div className="min-w-0 overflow-x-auto">
            <table className="min-w-full border-collapse">
              <caption className="mb-1 text-left text-sm font-medium">
                {s.previewHeading}
              </caption>
              <thead>
                <tr>
                  <th scope="col" className={cellClass}>
                    {s.line}
                  </th>
                  {preview.columns.map((c, i) => (
                    <th key={i} scope="col" className={cellClass}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.sample.map((row) => (
                  <tr key={row.line}>
                    <td className={cellClass}>{row.line}</td>
                    {preview.columns.map((_, i) => (
                      <td key={i} className={cellClass}>
                        {row.cells[i] ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!ready ? (
            <p className="text-sm text-red-700">{s.missing}</p>
          ) : (
            <>
              <p data-testid="import-summary" className="text-sm font-medium">
                {s.summary(importable, preview.errors.length)}
              </p>
              {preview.errors.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium">{s.errorsHeading}</h4>
                  <ul data-testid="import-errors" className="mt-1 space-y-1 text-sm text-error">
                    {preview.errors.map((e, i) => (
                      <li key={`${e.line}-${i}`}>
                        <span className="font-medium">{s.errorLine(e.line)}:</span> {e.message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {preview.holdings_after && importable > 0 && (
                <p className="text-xs text-muted">
                  {s.holdingsAfter}:{" "}
                  {preview.holdings_after.map((h) => `${h.ticker} ${h.quantity} ${h.currency}`).join(", ")}
                </p>
              )}
            </>
          )}

          {error && (
            <ErrorNotice
              title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
              message={error}
            />
          )}

          <div className="flex flex-wrap items-center gap-3">
            {importable > 0 && (
              <button
                type="button"
                disabled={busy}
                onClick={onImport}
                className="btn"
              >
                {busy ? s.importing : s.confirm(importable)}
              </button>
            )}
            <button type="button" onClick={reset} className={buttonClass}>
              {s.cancel}
            </button>
          </div>
        </div>
      )}
      {!preview && error && (
        <div className="mt-3">
          <ErrorNotice title={t.common.errors.heading} message={error} />
        </div>
      )}
    </section>
  );
}
