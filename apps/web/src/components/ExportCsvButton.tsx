"use client";

import { getMessages } from "@/i18n";
import { toCsv, type CsvTable } from "@/lib/csv";

/**
 * "Export CSV" for one result table: downloads `table` as `filename`. Pass the
 * result's `source.is_demo` as `demo` so synthetic data is marked in the file.
 * `label` names the table for screen readers ("Export Income statement as CSV").
 */
export function ExportCsvButton({
  table,
  filename,
  label,
  demo = false,
}: {
  table: CsvTable;
  filename: string;
  label: string;
  demo?: boolean;
}) {
  const t = getMessages().common.csv;

  function onClick() {
    // BOM so spreadsheet apps read the file as UTF-8.
    const blob = new Blob(["﻿", toCsv(table, { demo })], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={t.exportLabel(label)}
      className="btn btn-sm text-xs"
    >
      {t.export}
    </button>
  );
}
