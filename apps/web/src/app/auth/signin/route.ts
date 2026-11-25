import { NextResponse, type NextRequest } from "next/server";
import { authConfig, OAUTH_COOKIE, safeReturnTo, SESSION_COOKIE } from "@/lib/auth/config";
import { isHttps, productionOriginIfElsewhere, requestOrigin, seeOther } from "@/lib/auth/http";
import { beginSignIn, sealPending } from "@/lib/auth/oidc";
import { isSignedIn } from "@/lib/auth/session";

// GET /auth/signin?returnTo=/risk  ->  redirect to Google's consent screen.
// On a production deployment URL, start again on the production domain (the
// only redirect URI Google accepts). Already signed in: straight back to returnTo.
export async function GET(request: NextRequest) {
  const returnTo = safeReturnTo(request.nextUrl.searchParams.get("returnTo"));

  const production = productionOriginIfElsewhere(request);
  if (production) {
    return NextResponse.redirect(new URL(`/auth/signin?returnTo=${encodeURIComponent(returnTo)}`, production));
  }
  if (await isSignedIn(request.cookies.get(SESSION_COOKIE)?.value ?? null)) return seeOther(request, returnTo);

  const config = authConfig();
  if (!config) return seeOther(request, "/account?error=unavailable");

  const redirectUri = new URL("/auth/callback/google", requestOrigin(request)).toString();
  try {
    const { url, pending } = await beginSignIn(config, redirectUri, returnTo);
    const response = NextResponse.redirect(url);
    response.cookies.set(OAUTH_COOKIE, await sealPending(config, pending), {
      httpOnly: true,
      sameSite: "lax",
      secure: isHttps(request),
      path: "/auth/callback",
      maxAge: 600,
    });
    return response;
  } catch {
    return seeOther(request, "/account?error=signin");
  }
}
