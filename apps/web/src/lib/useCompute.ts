"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { postCompute, type ResultEnvelope } from "./envelope";

export type ComputeState<M extends string, S extends string> = {
  /** Last successful envelope. Kept while a newer request is invalid or failed. */
  result: ResultEnvelope<M, S> | null;
  /** Field-level validation messages from the latest request, keyed by request field. */
  fieldErrors: Record<string, string>;
  /** Request-level error message (validation summary or service failure). */
  error: string | null;
  pending: boolean;
};

/**
 * Keep a compute result in sync with a request body.
 * Runs immediately on mount (so pages show results on load), then re-runs,
 * debounced, whenever `body` changes. `run()` re-runs immediately (submit button).
 */
export function useCompute<M extends string, S extends string>(
  path: `/${string}`,
  body: unknown,
  debounceMs = 300,
): ComputeState<M, S> & { run: () => void } {
  const [state, setState] = useState<ComputeState<M, S>>({
    result: null,
    fieldErrors: {},
    error: null,
    pending: true,
  });
  const [nonce, setNonce] = useState(0);
  const immediate = useRef(true);
  const key = JSON.stringify(body);

  useEffect(() => {
    const controller = new AbortController();
    const delay = immediate.current ? 0 : debounceMs;
    immediate.current = false;
    const timer = setTimeout(async () => {
      setState((s) => ({ ...s, pending: true }));
      try {
        const outcome = await postCompute<M, S>(path, JSON.parse(key), controller.signal);
        if (controller.signal.aborted) return;
        setState((s) => {
          if (outcome.kind === "ok") return { result: outcome.result, fieldErrors: {}, error: null, pending: false };
          if (outcome.kind === "invalid")
            return { ...s, fieldErrors: outcome.fields, error: outcome.message, pending: false };
          return { ...s, fieldErrors: {}, error: outcome.message, pending: false };
        });
      } catch {
        // Aborted: a newer request superseded this one.
      }
    }, delay);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [path, key, nonce, debounceMs]);

  const run = useCallback(() => {
    immediate.current = true;
    setNonce((n) => n + 1);
  }, []);

  return { ...state, run };
}
