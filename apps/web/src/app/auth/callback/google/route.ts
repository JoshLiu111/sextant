import { type NextRequest } from "next/server";
import { authConfig, OAUTH_COOKIE } from "@/lib/auth/config";
import { requestOrigin, seeOther, setSessionCookie } from "@/lib/auth/http";
import { completeSignIn, openPending, signLoginAssertion } from "@/lib/auth/oidc";
import { computeFetch } from "@/lib/compute";

type SessionResponse = { token: string; expires_at: string };

// Google redirects here with ?code&state. Verify, then ask the compute
// service (which owns users and sessions) to open a session.
export async function GET(request: NextRequest) {
  const config = authConfig();
  if (!config) return seeOther(request, "/account?error=unavailable");

  const params = request.nextUrl.searchParams;
  const sealed = request.cookies.get(OAUTH_COOKIE)?.value;
  const code = params.get("code");
  const failed = () => {
    const response = seeOther(request, "/account?error=signin");
    response.cookies.delete({ name: OAUTH_COOKIE, path: "/auth/callback" });
    return response;
  };
  if (!sealed || !code || params.get("error")) return failed();

  try {
    const pending = await openPending(config, sealed);
    if (pending.state !== params.get("state")) return failed();
    const redirectUri = new URL("/auth/callback/google", requestOrigin(request)).toString();
    const identity = await completeSignIn(config, pending, code, redirectUri);

    const res = await computeFetch("/auth/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ assertion: await signLoginAssertion(config, identity) }),
      cache: "no-store",
    });
    if (res.status !== 201) return failed();
    const session = (await res.json()) as SessionResponse;

    const response = seeOther(request, pending.returnTo);
    response.cookies.delete({ name: OAUTH_COOKIE, path: "/auth/callback" });
    setSessionCookie(request, response, session.token, new Date(session.expires_at));
    return response;
  } catch {
    return failed();
  }
}
