import "server-only";

import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "./config";

/**
 * The origin the browser used. `request.nextUrl` can differ (e.g. the dev
 * server reports localhost for 127.0.0.1), which would break the OAuth
 * redirect URI and cookies, so trust the Host / X-Forwarded-* headers.
 */
export function requestOrigin(request: NextRequest): string {
  const host =
    request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? request.nextUrl.host;
  const proto =
    request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol.replace(/:$/, "");
  return `${proto.split(",")[0].trim()}://${host.split(",")[0].trim()}`;
}

/**
 * The production domain's origin when this request reached a production
 * deployment through another host (its deployment URL, e.g.
 * sextant-abc123-team.vercel.app), else null. Google only accepts the redirect
 * URI registered for the production domain, so sign-in has to start there.
 */
export function productionOriginIfElsewhere(request: NextRequest): string | null {
  const production = process.env.VERCEL_PROJECT_PRODUCTION_URL;
  if (process.env.VERCEL_ENV !== "production" || !production) return null;
  const origin = `https://${production}`;
  return requestOrigin(request) === origin ? null : origin;
}

/** Reject cross-site form posts (defence in depth on top of SameSite=Lax). */
export function isSameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  return origin === null || origin === requestOrigin(request);
}

export function isHttps(request: NextRequest): boolean {
  return requestOrigin(request).startsWith("https:");
}

/** 303 so a POSTed form lands on a GET page. */
export function seeOther(request: NextRequest, path: string): NextResponse {
  return NextResponse.redirect(new URL(path, requestOrigin(request)), 303);
}

export function setSessionCookie(
  request: NextRequest,
  response: NextResponse,
  token: string,
  expiresAt: Date,
) {
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: isHttps(request),
    path: "/",
    expires: expiresAt,
  });
}

export function clearSessionCookie(request: NextRequest, response: NextResponse) {
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: isHttps(request),
    path: "/",
    maxAge: 0,
  });
}
