import { NextResponse, type NextRequest } from "next/server";
import { authConfig, OAUTH_COOKIE, safeReturnTo } from "@/lib/auth/config";
import { isHttps, requestOrigin, seeOther } from "@/lib/auth/http";
import { beginSignIn, sealPending } from "@/lib/auth/oidc";

// GET /auth/signin?returnTo=/risk  ->  redirect to Google's consent screen.
export async function GET(request: NextRequest) {
  const config = authConfig();
  if (!config) return seeOther(request, "/account?error=unavailable");

  const returnTo = safeReturnTo(request.nextUrl.searchParams.get("returnTo"));
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
