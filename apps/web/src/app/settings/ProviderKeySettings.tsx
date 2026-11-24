"use client";

import { useState, type FormEvent } from "react";
import { ErrorNotice, FieldError, fieldErrorId } from "@/components/ErrorNotice";
import { getMessages } from "@/i18n";
import { providerKeysApi, type Provider, type SavedKey } from "@/lib/providerKeys";

type Notice = { kind: "status"; message: string } | { kind: "error"; message: string } | null;

/**
 * Save, replace or delete the signed-in user's key for one provider (Tiingo or
 * FMP). The key is checked with the provider before it is stored; afterwards
 * only its last four characters come back, and the input is cleared.
 */
export function ProviderKeySettings({ provider, initial }: { provider: Provider; initial: SavedKey | null }) {
  const shared = getMessages().settings.key;
  const t = getMessages().settings.providers[provider];
  const [saved, setSaved] = useState<SavedKey | null>(initial);
  const [key, setKey] = useState("");
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const inputId = `input-key-${provider}`;
  const errorName = `key-${provider}`;

  async function onSave(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    setFieldError(undefined);
    const outcome = await providerKeysApi.save(provider, key);
    setBusy(false);
    if (outcome.kind === "ok") {
      setSaved(outcome.value);
      setKey("");
      setNotice({ kind: "status", message: shared.savedStatus });
    } else if (outcome.kind === "invalid") {
      setFieldError(outcome.fields.key ?? outcome.message);
    } else {
      setNotice({ kind: "error", message: outcome.message });
    }
  }

  async function onDelete() {
    setBusy(true);
    setNotice(null);
    const outcome = await providerKeysApi.remove(provider);
    setBusy(false);
    setConfirming(false);
    if (outcome.kind === "ok") {
      setSaved(null);
      setNotice({ kind: "status", message: shared.deletedStatus });
    } else {
      setNotice({ kind: "error", message: outcome.message });
    }
  }

  return (
    <section
      aria-labelledby={`${provider}-key-heading`}
      className="mt-8 rounded-card border border-rule p-4"
    >
      <h2 id={`${provider}-key-heading`} className="text-lg">
        {t.heading}
      </h2>
      <p className="mt-1 text-sm text-ink-2">{t.body}</p>
      <p data-testid="key-status" className="mt-3 text-sm font-medium">
        {saved ? shared.saved(saved.hint) : shared.none}
      </p>

      <form onSubmit={onSave} className="mt-4 flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <label htmlFor={inputId} className="block text-sm font-medium">
            {t.label}
          </label>
          <input
            id={inputId}
            name="key"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            aria-invalid={fieldError ? true : undefined}
            aria-describedby={[`${inputId}-hint`, fieldError ? fieldErrorId(errorName) : null].filter(Boolean).join(" ")}
            className={`mt-1 w-full min-w-0 rounded-card border px-3 py-2 tabular-nums ${
              fieldError ? "border-error" : "border-muted"
            }`}
          />
          <p id={`${inputId}-hint`} className="mt-1 text-xs text-muted">
            {t.hint}
          </p>
          <FieldError name={errorName} message={fieldError} />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="btn btn-primary"
        >
          {saved ? shared.replace : shared.save}
        </button>
      </form>

      {busy && <p className="mt-3 text-sm text-muted">{t.saving}</p>}
      {notice?.kind === "status" && (
        <p role="status" className="mt-3 text-sm text-success">
          {notice.message}
        </p>
      )}
      {notice?.kind === "error" && (
        <div className="mt-3">
          <ErrorNotice title={shared.errorTitle} message={notice.message} />
        </div>
      )}

      {saved &&
        (confirming ? (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <p role="alert" className="w-full text-sm font-medium text-red-700">
              {shared.deleteWarning}
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={onDelete}
              className="btn btn-danger"
            >
              {shared.confirmDelete}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded-card border border-rule px-3 py-1.5 text-sm"
            >
              {shared.cancel}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="mt-4 rounded-card border border-error px-3 py-1.5 text-sm font-medium text-red-700"
          >
            {shared.delete}
          </button>
        ))}
    </section>
  );
}
