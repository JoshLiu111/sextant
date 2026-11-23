import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth/config";
import { isOperator } from "@/lib/operator";

// The operator view must answer a real HTTP 404 to everyone but operators. With
// cacheComponents the page streams a 200 before it can call notFound(), so the
// check happens here, before rendering. The page checks again on its own.
export async function proxy(request: NextRequest) {
  if (await isOperator(request.cookies.get(SESSION_COOKIE)?.value ?? null)) {
    return NextResponse.next();
  }
  // No route lives here, so Next renders the not-found page with status 404.
  return NextResponse.rewrite(new URL("/_operator-not-found", request.url));
}

export const config = {
  matcher: ["/operator", "/operator/:path*"],
};
