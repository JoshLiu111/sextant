// A stand-in for the ECB Data Portal API (data-api.ecb.europa.eu), for e2e tests
// only. Playwright starts it and points the compute service at it with
// ECB_BASE_URL, so the real ECB adapter runs end to end without the network. It
// serves the recordings the compute tests use (apps/compute/tests/fixtures/ecb/),
// with their Last-Modified headers, under the same routing rules as RecordedEcb
// in apps/compute/tests/ecb_fixtures.py: the recording is served whatever
// startPeriod a request sends; an unknown key answers 404.

import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.ECB_PORT || 9506);
const FIXTURES = fileURLToPath(new URL("../../compute/tests/fixtures/ecb/", import.meta.url));
const DATA_PATH = /^\/service\/data\/([A-Z0-9_]+)\/([A-Za-z0-9_.]+)$/;
const LAST_MODIFIED = JSON.parse(await readFile(`${FIXTURES}last_modified.json`, "utf8"));

createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ status: "ok" }));
  }
  const match = DATA_PATH.exec(url.pathname);
  if (!match || url.searchParams.get("format") !== "csvdata") {
    res.writeHead(400, { "content-type": "text/plain" });
    return res.end("Bad request");
  }
  const [, flow, key] = match;
  let body;
  try {
    body = await readFile(`${FIXTURES}${flow}/${key}.csv`);
  } catch {
    res.writeHead(404, { "content-type": "application/json" });
    return res.end('{"detail":"No Series was returned for the query","status":404,"title":"Not Found"}');
  }
  const headers = { "content-type": "text/csv" };
  const modified = LAST_MODIFIED[`${flow}/${key}`];
  if (modified) headers["last-modified"] = modified;
  res.writeHead(200, headers);
  res.end(body);
}).listen(PORT, "127.0.0.1");
