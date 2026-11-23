// A stand-in for api.worldbank.org's Indicators API v2, for e2e tests only.
// Playwright starts it and points the compute service at it with
// WORLD_BANK_BASE_URL, so the real World Bank adapter runs end to end without
// the network. It serves the recordings the compute tests use
// (apps/compute/tests/fixtures/world_bank/), with the same routing rules as
// RecordedWorldBank in apps/compute/tests/world_bank_fixtures.py: whatever
// countries and years a data request names, the indicator's recording is served.

import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.WORLD_BANK_PORT || 9505);
const FIXTURES = fileURLToPath(new URL("../../compute/tests/fixtures/world_bank/", import.meta.url));
const DATA_PATH = /^\/v2\/country\/[^/]+\/indicator\/([^/]+)$/;
const METADATA_PATH = /^\/v2\/sources\/2\/series\/([^/]+)\/metadata$/;
const INVALID_VALUE =
  '[{"message":[{"id":"120","key":"Invalid value","value":"The provided parameter value is not valid"}]}]';

async function recording(dir, id) {
  try {
    return await readFile(`${FIXTURES}${dir}/${id}.json`, "utf8");
  } catch {
    return null;
  }
}

createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ status: "ok" }));
  }
  const data = DATA_PATH.exec(url.pathname);
  const metadata = METADATA_PATH.exec(url.pathname);
  if (url.searchParams.get("format") !== "json" || (!data && !metadata)) {
    res.writeHead(404, { "content-type": "text/plain" });
    return res.end("Not found");
  }
  const body = data ? await recording("indicators", data[1]) : await recording("metadata", metadata[1]);
  res.writeHead(200, { "content-type": "application/json;charset=utf-8" });
  res.end(body ?? INVALID_VALUE);
}).listen(PORT, "127.0.0.1");
