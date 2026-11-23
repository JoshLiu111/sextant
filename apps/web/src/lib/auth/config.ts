import "server-only";

// Sign-in settings, all from environment variables (never committed):
//   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET  Google OAuth client (web application)
//   SESSION_SECRET                          shared with the compute service, >= 32 chars
//   OIDC_ISSUER                             optional; defaults to Google. e2e points it
//                                           at a local fake provider.

/** Same name the compute service reads, so browser calls to /api/compute carry it. */
export const SESSION_COOKIE = "sextant_session";
/** Short-lived cookie holding state, nonce and PKCE verifier during sign-in. */
export const OAUTH_COOKIE = "sextant_oauth";

export const GOOGLE_ISSUER = "https://accounts.google.com";

export type AuthConfig = {
  clientId: string;
  clientSecret: string;
  sessionSecret: Uint8Array;
  issuer: string;
};

export function authConfig(): AuthConfig | null {
  const clientId = process.env.GOOGLE_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET;
  const sessionSecret = process.env.SESSION_SECRET;
  if (!clientId || !clientSecret || !sessionSecret || sessionSecret.length < 32) return null;
  return {
    clientId,
    clientSecret,
    sessionSecret: new TextEncoder().encode(sessionSecret),
    issuer: process.env.OIDC_ISSUER || GOOGLE_ISSUER,
  };
}

/** Only same-site paths, never protocol-relative URLs or the auth routes themselves. */
export function safeReturnTo(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) {
    return "/";
  }
  if (value.startsWith("/auth/")) return "/";
  return value;
}
