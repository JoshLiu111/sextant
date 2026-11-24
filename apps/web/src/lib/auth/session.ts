import "server-only";

import { cookies } from "next/headers";
import { cache } from "react";
import { computeFetch } from "@/lib/compute";
import { SESSION_COOKIE } from "./config";

// "Who is the user" on the web side. The compute service owns users and
// sessions; the browser holds only the opaque session token in an httpOnly
// cookie. Server code forwards it as a Bearer token.

export type CurrentUser = { id: string; email: string; name: string | null };

export async function sessionToken(): Promise<string | null> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}

/**
 * The signed-in user, or null. Reads the request cookie, so call it only
 * inside a <Suspense> boundary (cacheComponents). Deduplicated per request.
 */
export const getCurrentUser = cache(async (): Promise<CurrentUser | null> => {
  const token = await sessionToken();
  if (!token) return null;
  try {
    const res = await computeFetchAsUser(token, "/me", { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return null;
    return (await res.json()) as CurrentUser;
  } catch {
    return null;
  }
});

/**
 * True when `token` is a live session. For the proxy, which has the cookie but
 * no React request scope. Any failure counts as "no".
 */
export function isSignedIn(token: string | null): Promise<boolean> {
  return answersAsUser(token, "/me", (res) => res.ok);
}

/**
 * Whether `path`, called on behalf of `token`, answers as `accepted` says
 * (within 5 s). No token, a timeout or any other failure counts as "no".
 */
export async function answersAsUser(
  token: string | null,
  path: `/${string}`,
  accepted: (res: Response) => boolean,
): Promise<boolean> {
  if (!token) return false;
  try {
    return accepted(await computeFetchAsUser(token, path, { signal: AbortSignal.timeout(5000) }));
  } catch {
    return false;
  }
}

/** Server-side call to the compute service on behalf of the user holding `token`. */
export function computeFetchAsUser(
  token: string,
  path: `/${string}`,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("authorization", `Bearer ${token}`);
  return computeFetch(path, { cache: "no-store", ...init, headers });
}
