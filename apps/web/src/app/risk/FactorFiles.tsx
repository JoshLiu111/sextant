"use client";

import { useEffect, useState, type ChangeEvent } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { getMessages } from "@/i18n";
import { factorFilesApi, type FactorFile } from "@/lib/factorFiles";

type Notice = { kind: "status"; message: string } | { kind: "error"; message: string } | null;

/**
 * The signed-in user's own factor files for factor regressions on My data (ADR 0003).
 * RiskTool shows it only in My data mode, which only users with a provider key reach.
 * `onChange` runs after an upload or a removal, so the results recompute.
 */
export function FactorFiles({ onChange }: { onChange: () => void }) {
  const t = getMessages().risk.factorFiles;
  const [files, setFiles] = useState<FactorFile[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    factorFilesApi.list().then((outcome) => {
      if (live && outcome.kind === "ok") setFiles(outcome.value);
    });
    return () => {
      live = false;
    };
  }, []);

  async function onUpload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    setBusy(true);
    setNotice(null);
    const outcome = await factorFilesApi.upload(file.name, await file.text());
    input.value = "";
    setBusy(false);
    if (outcome.kind === "ok") {
      const saved = outcome.value;
      setFiles((all) => [...all.filter((f) => f.kind !== saved.kind), saved].sort((a, b) => b.kind.localeCompare(a.kind)));
      setNotice({ kind: "status", message: t.uploaded(saved.filename) });
      onChange();
    } else {
      setNotice({ kind: "error", message: outcome.message });
    }
  }

  async function onRemove(file: FactorFile) {
    setBusy(true);
    setNotice(null);
    const outcome = await factorFilesApi.remove(file.kind);
    setBusy(false);
    if (outcome.kind === "ok") {
      setFiles((all) => all.filter((f) => f.kind !== file.kind));
      setNotice({ kind: "status", message: t.removed(file.filename) });
      onChange();
    } else {
      setNotice({ kind: "error", message: outcome.message });
    }
  }

  return (
    <section aria-labelledby="factor-files-heading" className="well p-3">
      <h3 id="factor-files-heading" className="font-body text-sm font-medium tracking-normal">
        {t.heading}
      </h3>
      <p className="hint mt-1">{t.body}</p>
      <ul className="mt-2 space-y-2 text-sm">
        {files.map((file) => (
          <li key={file.kind} data-testid={`factor-file-${file.kind}`} className="flex items-start justify-between gap-2">
            <span className="min-w-0 break-words">
              <span className="font-medium">{t.kinds[file.kind]}:</span> {file.filename} ({t.frequency[file.frequency]},{" "}
              {file.first} {t.to} {file.last})
            </span>
            <button
              type="button"
              disabled={busy}
              onClick={() => onRemove(file)}
              aria-label={t.remove(t.kinds[file.kind])}
              className="btn btn-sm shrink-0"
            >
              {t.removeShort}
            </button>
          </li>
        ))}
      </ul>
      {files.length === 0 && <p className="mt-2 text-sm">{t.none}</p>}
      <label htmlFor="factor-file-input" className="label mt-3">
        {t.upload}
      </label>
      <input
        id="factor-file-input"
        type="file"
        accept=".csv,.CSV,.txt,text/csv"
        disabled={busy}
        onChange={onUpload}
        aria-describedby="factor-file-hint"
        className="mt-1 block w-full text-sm"
      />
      <p id="factor-file-hint" className="hint mt-1">
        {t.hint}
      </p>
      {notice?.kind === "status" && (
        <p role="status" className="mt-2 text-sm text-success">
          {notice.message}
        </p>
      )}
      {notice?.kind === "error" && (
        <div className="mt-2">
          <ErrorNotice title={t.errorTitle} message={notice.message} />
        </div>
      )}
    </section>
  );
}
