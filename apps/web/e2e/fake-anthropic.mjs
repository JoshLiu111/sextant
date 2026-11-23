// A stand-in for the Claude Messages API (api.anthropic.com/v1/messages), for
// e2e tests only. Playwright starts it and points the compute service at it with
// ANTHROPIC_BASE_URL, so the real Claude client runs end to end without the
// network or a real key.
//
// It answers deterministically from the result JSON in the prompt. For a single-option
// result it quotes the call price the compute service calculated, and mentions
// buying so the not-advice notice shows. For any other tool it names the tool,
// counts the metrics computed, and says so when the result is demo data.

import { createServer } from "node:http";

const PORT = Number(process.env.ANTHROPIC_PORT || 9600);

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function resultFrom(prompt) {
  const match = /Result \(JSON\):\n([\s\S]*?)\n\nExplain this result\./.exec(prompt);
  return match ? JSON.parse(match[1]) : null;
}

function answer(result) {
  if (!result) return "I could not find a result in this prompt.";
  const call = result.metrics?.call_price?.value;
  if (call != null) {
    return (
      `With these inputs the call is worth about ${call.toFixed(2)} per share.\n\n` +
      "Someone thinking of buying it would compare that with the market price."
    );
  }
  const metrics = Object.values(result.metrics ?? {});
  const ok = metrics.filter((m) => m.status === "ok").length;
  const demo = result.source?.is_demo ? " This result uses synthetic demo data, not real market data." : "";
  return `This ${result.tool} result has ${ok} of ${metrics.length} metrics computed.${demo}`;
}

createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/health") return send(res, 200, { status: "ok" });
  if (url.pathname !== "/v1/messages" || req.method !== "POST") {
    return send(res, 404, { type: "error", error: { type: "not_found_error", message: "Not found" } });
  }
  if (!req.headers["x-api-key"]) {
    return send(res, 401, { type: "error", error: { type: "authentication_error", message: "x-api-key header is required" } });
  }
  let raw = "";
  req.on("data", (chunk) => (raw += chunk));
  req.on("end", () => {
    const body = JSON.parse(raw);
    const prompt = body.messages?.[0]?.content ?? "";
    const result = resultFrom(prompt);
    const text = answer(result);
    send(res, 200, {
      id: "msg_fake",
      type: "message",
      role: "assistant",
      model: body.model,
      content: [{ type: "text", text }],
      stop_reason: "end_turn",
      usage: { input_tokens: Math.ceil(prompt.length / 4), output_tokens: Math.ceil(text.length / 4) },
    });
  });
}).listen(PORT, "127.0.0.1");
