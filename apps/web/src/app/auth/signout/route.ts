import { type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth/config";
import { clearSessionCookie, isSameOrigin, seeOther } from "@/lib/auth/http";
import { computeFetchAsUser } from "@/lib/auth/session";

// POST /auth/signout (a plain form in the nav): end the session everywhere.
export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return new Response("Forbidden", { status: 403 });

  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) {
    // Best effort: the cookie is cleared even if the compute call fails.
    await computeFetchAsUser(token, "/auth/session", { method: "DELETE" }).catch(() => null);
  }
  const response = seeOther(request, "/");
  clearSessionCookie(request, response);
  return response;
}
