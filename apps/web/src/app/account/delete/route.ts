import { type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth/config";
import { clearSessionCookie, isSameOrigin, seeOther } from "@/lib/auth/http";
import { computeFetchAsUser } from "@/lib/auth/session";

// POST /account/delete (the confirmed form on /account): delete the user and,
// by ON DELETE CASCADE in the compute database, all user-owned rows.
export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return new Response("Forbidden", { status: 403 });

  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return seeOther(request, "/account");

  const res = await computeFetchAsUser(token, "/me", { method: "DELETE" }).catch(() => null);
  if (!res || (res.status !== 204 && res.status !== 401)) {
    return seeOther(request, "/account?error=delete");
  }
  // 401: the session had already ended, so there is nothing left to delete as this user.
  const response = seeOther(request, res.status === 204 ? "/account?deleted=1" : "/account");
  clearSessionCookie(request, response);
  return response;
}
