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
      className="mt-8 rounded-lg border border-black/10 p-4 dark:border-white/15"
    >
      <h2 id={`${provider}-key-heading`} className="font-semibold">
        {t.heading}
      </h2>
      <p className="mt-1 text-sm text-black/70 dark:text-white/70">{t.body}</p>
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
            className={`mt-1 w-full min-w-0 rounded-md border px-3 py-2 font-mono dark:bg-white/5 ${
              fieldError ? "border-red-500" : "border-black/20 dark:border-white/20"
            }`}
          />
          <p id={`${inputId}-hint`} className="mt-1 text-xs text-black/50 dark:text-white/50">
            {t.hint}
          </p>
          <FieldError name={errorName} message={fieldError} />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-black px-3 py-2 text-sm font-medium text-white hover:bg-black/80 disabled:opacity-50 dark:bg-white dark:text-black"
        >
          {saved ? shared.replace : shared.save}
        </button>
      </form>

      {busy && <p className="mt-3 text-sm text-black/60 dark:text-white/60">{t.saving}</p>}
      {notice?.kind === "status" && (
        <p role="status" className="mt-3 text-sm text-green-800 dark:text-green-300">
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
            <p role="alert" className="w-full text-sm font-medium text-red-700 dark:text-red-400">
              {shared.deleteWarning}
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={onDelete}
              className="rounded bg-red-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {shared.confirmDelete}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded border border-black/15 px-3 py-1.5 text-sm dark:border-white/20"
            >
              {shared.cancel}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="mt-4 rounded border border-red-700 px-3 py-1.5 text-sm font-medium text-red-700 dark:text-red-400"
          >
            {shared.delete}
          </button>
        ))}
    </section>
  );
}
