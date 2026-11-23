// A stand-in for the Tiingo API (api.tiingo.com), for e2e tests only.
// Playwright starts it and points the compute service at it with
// TIINGO_BASE_URL. It answers GET /api/test the way real Tiingo does (checked
// 2026-11-22): always HTTP 200, with a message saying whether the token worked.
//
// Tokens starting with "good" are valid. A token starting with "outage" makes
// it answer 503, to stand in for Tiingo being down. Anything else is rejected.

import { createServer } from "node:http";

const PORT = Number(process.env.TIINGO_PORT || 9600);

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/health") return send(res, 200, { status: "ok" });
  if (url.pathname !== "/api/test") return send(res, 404, { detail: "Not found." });
  const auth = req.headers.authorization || "";
  if (!auth) return send(res, 200, { message: "'AUTHORIZATION header' was not set" });
  const token = auth.replace(/^Token /, "");
  if (token.startsWith("outage")) return send(res, 503, { detail: "Service Unavailable" });
  if (token.startsWith("good")) return send(res, 200, { message: "You successfully sent a request" });
  send(res, 200, { message: "Auth Token was not correct" });
}).listen(PORT, "127.0.0.1");
