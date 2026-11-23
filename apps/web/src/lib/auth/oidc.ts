import "server-only";

import { createHash, randomBytes } from "node:crypto";
import { createRemoteJWKSet, jwtVerify, SignJWT } from "jose";
import { GOOGLE_ISSUER, type AuthConfig } from "./config";

// Google OpenID Connect, authorization code flow with PKCE, state and nonce.
// Sextant verifies the ID token itself and then issues its own session.

type Discovery = {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  jwks_uri: string;
};

const discoveries = new Map<string, Promise<Discovery>>();
const jwkSets = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

function discover(issuer: string): Promise<Discovery> {
  let found = discoveries.get(issuer);
  if (!found) {
    found = fetch(`${issuer}/.well-known/openid-configuration`, { cache: "no-store" }).then(
      async (res) => {
        if (!res.ok) throw new Error(`OIDC discovery failed: ${res.status}`);
        return (await res.json()) as Discovery;
      },
    );
    found.catch(() => discoveries.delete(issuer));
    discoveries.set(issuer, found);
  }
  return found;
}

function jwks(uri: string) {
  let set = jwkSets.get(uri);
  if (!set) {
    set = createRemoteJWKSet(new URL(uri));
    jwkSets.set(uri, set);
  }
  return set;
}

const random = () => randomBytes(32).toString("base64url");

export type PendingSignIn = { state: string; nonce: string; verifier: string; returnTo: string };

/** Start sign-in: the provider URL to redirect to, and what to remember in a cookie. */
export async function beginSignIn(config: AuthConfig, redirectUri: string, returnTo: string) {
  const { authorization_endpoint } = await discover(config.issuer);
  const pending: PendingSignIn = { state: random(), nonce: random(), verifier: random(), returnTo };
  const url = new URL(authorization_endpoint);
  url.search = new URLSearchParams({
    client_id: config.clientId,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: "openid email profile",
    state: pending.state,
    nonce: pending.nonce,
    code_challenge: createHash("sha256").update(pending.verifier).digest("base64url"),
    code_challenge_method: "S256",
    prompt: "select_account",
  }).toString();
  return { url, pending };
}

/** Seal the pending sign-in into a signed, 10-minute cookie value. */
export function sealPending(config: AuthConfig, pending: PendingSignIn): Promise<string> {
  return new SignJWT({ ...pending })
    .setProtectedHeader({ alg: "HS256" })
    .setAudience("sextant-oauth")
    .setIssuedAt()
    .setExpirationTime("10m")
    .sign(config.sessionSecret);
}

export async function openPending(config: AuthConfig, sealed: string): Promise<PendingSignIn> {
  const { payload } = await jwtVerify(sealed, config.sessionSecret, { audience: "sextant-oauth" });
  return payload as unknown as PendingSignIn;
}

export type GoogleIdentity = { sub: string; email: string; name: string | null };

/** Exchange the code and verify the ID token (signature, issuer, audience, nonce). */
export async function completeSignIn(
  config: AuthConfig,
  pending: PendingSignIn,
  code: string,
  redirectUri: string,
): Promise<GoogleIdentity> {
  const discovery = await discover(config.issuer);
  const res = await fetch(discovery.token_endpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: redirectUri,
      client_id: config.clientId,
      client_secret: config.clientSecret,
      code_verifier: pending.verifier,
    }),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Token exchange failed: ${res.status}`);
  const { id_token } = (await res.json()) as { id_token?: string };
  if (!id_token) throw new Error("No ID token in token response");

  const issuers =
    config.issuer === GOOGLE_ISSUER ? [GOOGLE_ISSUER, "accounts.google.com"] : [discovery.issuer];
  const { payload } = await jwtVerify(id_token, jwks(discovery.jwks_uri), {
    issuer: issuers,
    audience: config.clientId,
  });
  if (payload.nonce !== pending.nonce) throw new Error("Nonce mismatch");
  if (typeof payload.email !== "string" || payload.email_verified !== true) {
    throw new Error("Google account has no verified email");
  }
  return {
    sub: payload.sub!,
    email: payload.email,
    name: typeof payload.name === "string" ? payload.name : null,
  };
}

/** The short-lived proof the compute service exchanges for a session (see ADR 0001). */
export function signLoginAssertion(config: AuthConfig, identity: GoogleIdentity): Promise<string> {
  return new SignJWT({ email: identity.email, name: identity.name })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuer("sextant-web")
    .setAudience("sextant-compute")
    .setSubject(identity.sub)
    .setIssuedAt()
    .setExpirationTime("60s")
    .sign(config.sessionSecret);
}
