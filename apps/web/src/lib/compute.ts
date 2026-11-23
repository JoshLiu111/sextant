// How the frontend reaches the Python compute service.
//
// Every compute route lives under COMPUTE_PREFIX ("/api/compute/...").
// - Browser code: call the relative path (`computePath("/health")`). On Vercel,
//   the top-level rewrite in vercel.json sends it to the compute service; in
//   local dev, next.config.ts proxies it to COMPUTE_URL.
// - Server code: use `computeFetch`, which goes direct to the service via the
//   Vercel service binding (COMPUTE_INTERNAL_URL) or COMPUTE_URL locally.

export const COMPUTE_PREFIX = "/api/compute";

const LOCAL_COMPUTE_URL = "http://127.0.0.1:8000";

export function computePath(path: `/${string}`): string {
  return `${COMPUTE_PREFIX}${path}`;
}

export function computeBaseUrl(): string {
  return process.env.COMPUTE_INTERNAL_URL || process.env.COMPUTE_URL || LOCAL_COMPUTE_URL;
}

/** Server-only fetch against the compute service. */
export function computeFetch(path: `/${string}`, init?: RequestInit): Promise<Response> {
  return fetch(new URL(computePath(path), computeBaseUrl()), init);
}

export type ComputeHealth = { status: "ok"; service: string; version: string };

export async function getComputeHealth(): Promise<ComputeHealth | null> {
  try {
    const res = await computeFetch("/health", {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    const body = (await res.json()) as ComputeHealth;
    return body.status === "ok" ? body : null;
  } catch {
    return null;
  }
}
