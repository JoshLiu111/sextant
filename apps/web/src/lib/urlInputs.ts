"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

/**
 * Shareable links (spec story 10): how one tool's form maps to and from the
 * query string. Values are in the form's display units (percent, USD millions),
 * exactly as the visitor typed them, so a link reads like the form.
 *
 * - `read` fills anything missing from the tool's defaults. It never rejects a
 *   value: a bad one goes into the form as typed and the API's normal
 *   validation error shows inline.
 * - `write` returns the params for the current inputs (null = leave out).
 * - `keys` are the params this tool owns; writing replaces exactly those, so two
 *   tools on one page (Company Health Check) can share the query string.
 */
export type UrlCodec<F> = {
  keys: readonly string[];
  read: (params: URLSearchParams) => F;
  write: (form: F) => Record<string, string | null>;
};

/**
 * Codec for a flat form of string fields, one param per field, named after the
 * field (and so after the request field). Every field is written, so a link
 * keeps meaning the same thing if the defaults change later. A field left empty
 * whose default is not empty is written as `name=` so it stays empty on load.
 */
export function fieldsCodec<F extends Record<string, string>>(defaults: F): UrlCodec<F> {
  const keys = Object.keys(defaults) as (keyof F & string)[];
  return {
    keys,
    read(params) {
      const form = { ...defaults };
      for (const key of keys) {
        const raw = params.get(key);
        if (raw !== null) form[key] = raw as F[typeof key];
      }
      return form;
    },
    write(form) {
      const out: Record<string, string | null> = {};
      for (const key of keys) out[key] = form[key] === "" && defaults[key] === "" ? null : form[key];
      return out;
    },
  };
}

/** Rows of fields as one param: `DEMO-A:40,DEMO-B:30`. */
export function encodeRows(rows: readonly (readonly string[])[]): string {
  return rows.map((row) => row.map((v) => v.trim()).join(":")).join(",");
}

/** Inverse of `encodeRows`; each row is padded with "" to `width` fields. */
export function decodeRows(raw: string, width: number): string[][] {
  if (raw.trim() === "") return [];
  return raw.split(",").map((row) => {
    const fields = row.split(":");
    return Array.from({ length: width }, (_, i) => fields[i] ?? "");
  });
}

/** Query string with `,` and `:` left readable (both are legal in a query). */
function toQuery(params: URLSearchParams): string {
  return params.toString().replace(/%2C/gi, ",").replace(/%3A/gi, ":");
}

/** Replace the codec's params in the address bar, keeping any others. */
export function writeUrlInputs<F>(codec: UrlCodec<F>, form: F) {
  const params = new URLSearchParams(window.location.search);
  for (const key of codec.keys) params.delete(key);
  for (const [key, value] of Object.entries(codec.write(form))) if (value !== null) params.set(key, value);
  const query = toQuery(params);
  window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
}

/**
 * The tool's inputs as the URL gives them on load, and a `share` function to
 * call on submit. Uses `useSearchParams`, so render the tool inside `<Suspense>`.
 */
export function useUrlInputs<F>(codec: UrlCodec<F>): { initial: F; share: (form: F) => void } {
  const params = useSearchParams();
  const [initial] = useState(() => codec.read(new URLSearchParams(params.toString())));
  return { initial, share: (form: F) => writeUrlInputs(codec, form) };
}
