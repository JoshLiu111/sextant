// A tiny stand-in for Google's OpenID Connect provider, for e2e tests only.
// Playwright starts it (see playwright.config.ts) and points the web app at it
// with OIDC_ISSUER, so sign-in is tested end to end without touching Google.
//
// /authorize shows an "account chooser" form: the test types any email, and
// that email becomes the identity (sub = "fake-" + email). Each test can
// therefore use its own account and run in parallel.

import { createHash, randomBytes } from "node:crypto";
import { createServer } from "node:http";
import { SignJWT, exportJWK, generateKeyPair } from "jose";

const PORT = Number(process.env.OIDC_PORT || 9400);
const ISSUER = `http://127.0.0.1:${PORT}`;
const CLIENT_ID = process.env.GOOGLE_CLIENT_ID || "e2e-client-id";
const CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET || "e2e-client-secret";

const { publicKey, privateKey } = await generateKeyPair("RS256");
const jwk = { ...(await exportJWK(publicKey)), kid: "fake-1", alg: "RS256", use: "sig" };
const codes = new Map();

function send(res, status, body, headers = {}) {
  const isJson = typeof body !== "string";
  res.writeHead(status, {
    "content-type": isJson ? "application/json" : "text/html; charset=utf-8",
    ...headers,
  });
  res.end(isJson ? JSON.stringify(body) : body);
}

async function readForm(req) {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return new URLSearchParams(raw);
}

const escape = (s) => String(s).replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);

createServer(async (req, res) => {
  const url = new URL(req.url, ISSUER);

  if (url.pathname === "/.well-known/openid-configuration") {
    return send(res, 200, {
      issuer: ISSUER,
      authorization_endpoint: `${ISSUER}/authorize`,
      token_endpoint: `${ISSUER}/token`,
      jwks_uri: `${ISSUER}/jwks`,
    });
  }

  if (url.pathname === "/jwks") return send(res, 200, { keys: [jwk] });

  if (url.pathname === "/authorize" && req.method === "GET") {
    const p = url.searchParams;
    if (p.get("client_id") !== CLIENT_ID) return send(res, 400, "unknown client_id");
    const hidden = ["redirect_uri", "state", "nonce", "code_challenge"]
      .map((k) => `<input type="hidden" name="${k}" value="${escape(p.get(k) ?? "")}">`)
      .join("");
    return send(
      res,
      200,
      `<!doctype html><title>Fake Google</title><h1>Choose an account</h1>
       <form method="post" action="/authorize">${hidden}
         <label>Email <input name="email" type="email" required></label>
         <label>Name <input name="name"></label>
         <button type="submit">Continue</button>
       </form>`,
    );
  }

  if (url.pathname === "/authorize" && req.method === "POST") {
    const f = await readForm(req);
    const code = randomBytes(16).toString("hex");
    codes.set(code, {
      email: f.get("email"),
      name: f.get("name") || null,
      nonce: f.get("nonce"),
      challenge: f.get("code_challenge"),
      redirectUri: f.get("redirect_uri"),
    });
    const back = new URL(f.get("redirect_uri"));
    back.searchParams.set("code", code);
    back.searchParams.set("state", f.get("state"));
    return send(res, 302, "", { location: back.toString() });
  }

  if (url.pathname === "/token" && req.method === "POST") {
    const f = await readForm(req);
    const grant = codes.get(f.get("code"));
    codes.delete(f.get("code"));
    const challenge = createHash("sha256").update(f.get("code_verifier") ?? "").digest("base64url");
    if (
      !grant ||
      f.get("client_id") !== CLIENT_ID ||
      f.get("client_secret") !== CLIENT_SECRET ||
      f.get("redirect_uri") !== grant.redirectUri ||
      challenge !== grant.challenge
    ) {
      return send(res, 400, { error: "invalid_grant" });
    }
    const idToken = await new SignJWT({
      email: grant.email,
      email_verified: true,
      name: grant.name,
      nonce: grant.nonce,
    })
      .setProtectedHeader({ alg: "RS256", kid: jwk.kid })
      .setIssuer(ISSUER)
      .setAudience(CLIENT_ID)
      .setSubject(`fake-${grant.email}`)
      .setIssuedAt()
      .setExpirationTime("5m")
      .sign(privateKey);
    return send(res, 200, { id_token: idToken, access_token: "fake", token_type: "Bearer" });
  }

  send(res, 404, { error: "not_found" });
}).listen(PORT, "127.0.0.1", () => console.log(`fake OIDC provider on ${ISSUER}`));
