import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth/config";
import { isSignedIn } from "@/lib/auth/session";
import { isOperator } from "@/lib/operator";

// Checks that must happen before rendering:
//
// - `/`: signed-in users go to their dashboard. Without a session cookie the
//   request passes straight through with no compute call, so the landing page
//   stays static. With a cookie, compute confirms the session first, so a stale
//   or revoked cookie falls through to the landing page and can't loop with the
//   dashboard's own redirect back to `/`.
// - `/dashboard`: visitors without a session cookie go to `/`. The page checks
//   the session again and redirects on its own when the cookie is no good.
// - `/operator`: must answer a real HTTP 404 to everyone but operators. With
//   cacheComponents the page streams a 200 before it can call notFound(), so
//   the check happens here. The page checks again on its own.
export async function proxy(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value ?? null;
  const { pathname } = request.nextUrl;

  if (pathname === "/") {
    if (token && (await isSignedIn(token))) return redirectTo(request, "/dashboard");
    return NextResponse.next();
  }
  if (pathname === "/dashboard") {
    return token ? NextResponse.next() : redirectTo(request, "/");
  }

  if (await isOperator(token)) return NextResponse.next();
  // No route lives here, so Next renders the not-found page with status 404.
  return NextResponse.rewrite(new URL("/_operator-not-found", request.url));
}

function redirectTo(request: NextRequest, path: "/" | "/dashboard") {
  return NextResponse.redirect(new URL(path, request.url));
}

export const config = {
  matcher: ["/", "/dashboard", "/operator", "/operator/:path*"],
};
