"use client";

import { useState, type FormEvent } from "react";
import { ErrorNotice, FieldError, fieldErrorId } from "@/components/ErrorNotice";
import { getMessages } from "@/i18n";
import { providerKeysApi, type SavedKey } from "@/lib/providerKeys";

type Notice = { kind: "status"; message: string } | { kind: "error"; message: string } | null;

/**
 * Save, replace or delete the signed-in user's Tiingo key. The key is checked
 * with Tiingo before it is stored; afterwards only its last four characters
 * come back, and the input is cleared.
 */
export function TiingoKeySettings({ initial }: { initial: SavedKey | null }) {
  const t = getMessages().settings.tiingo;
  const [saved, setSaved] = useState<SavedKey | null>(initial);
  const [key, setKey] = useState("");
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function onSave(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    setFieldError(undefined);
    const outcome = await providerKeysApi.save("tiingo", key);
    setBusy(false);
    if (outcome.kind === "ok") {
      setSaved(outcome.value);
      setKey("");
      setNotice({ kind: "status", message: t.savedStatus });
    } else if (outcome.kind === "invalid") {
      setFieldError(outcome.fields.key ?? outcome.message);
    } else {
      setNotice({ kind: "error", message: outcome.message });
    }
  }

  async function onDelete() {
    setBusy(true);
    setNotice(null);
    const outcome = await providerKeysApi.remove("tiingo");
    setBusy(false);
    setConfirming(false);
    if (outcome.kind === "ok") {
      setSaved(null);
      setNotice({ kind: "status", message: t.deletedStatus });
    } else {
      setNotice({ kind: "error", message: outcome.message });
    }
  }

  return (
    <section aria-labelledby="tiingo-key-heading" className="mt-8 rounded-lg border border-black/10 p-4 dark:border-white/15">
      <h2 id="tiingo-key-heading" className="font-semibold">
        {t.heading}
      </h2>
      <p className="mt-1 text-sm text-black/70 dark:text-white/70">{t.body}</p>
      <p data-testid="key-status" className="mt-3 text-sm font-medium">
        {saved ? t.saved(saved.hint) : t.none}
      </p>

      <form onSubmit={onSave} className="mt-4 flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <label htmlFor="input-key" className="block text-sm font-medium">
            {t.label}
          </label>
          <input
            id="input-key"
            name="key"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            aria-invalid={fieldError ? true : undefined}
            aria-describedby={["input-key-hint", fieldError ? fieldErrorId("key") : null].filter(Boolean).join(" ")}
            className={`mt-1 w-full min-w-0 rounded-md border px-3 py-2 font-mono dark:bg-white/5 ${
              fieldError ? "border-red-500" : "border-black/20 dark:border-white/20"
            }`}
          />
          <p id="input-key-hint" className="mt-1 text-xs text-black/50 dark:text-white/50">
            {t.hint}
          </p>
          <FieldError name="key" message={fieldError} />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-black px-3 py-2 text-sm font-medium text-white hover:bg-black/80 disabled:opacity-50 dark:bg-white dark:text-black"
        >
          {saved ? t.replace : t.save}
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
          <ErrorNotice title={t.errorTitle} message={notice.message} />
        </div>
      )}

      {saved &&
        (confirming ? (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <p role="alert" className="w-full text-sm font-medium text-red-700 dark:text-red-400">
              {t.deleteWarning}
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={onDelete}
              className="rounded bg-red-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {t.confirmDelete}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded border border-black/15 px-3 py-1.5 text-sm dark:border-white/20"
            >
              {t.cancel}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="mt-4 rounded border border-red-700 px-3 py-1.5 text-sm font-medium text-red-700 dark:text-red-400"
          >
            {t.delete}
          </button>
        ))}
    </section>
  );
}
