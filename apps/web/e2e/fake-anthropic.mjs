// A stand-in for the Claude Messages API (api.anthropic.com/v1/messages), for
// e2e tests only. Playwright starts it and points the compute service at it with
// ANTHROPIC_BASE_URL, so the real Claude client runs end to end without the
// network or a real key.
//
// It answers deterministically from the result JSON in the prompt: it quotes the
// call price the compute service calculated, and mentions buying so the
// not-advice notice shows.

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
    const call = result?.metrics?.call_price?.value;
    const text =
      call == null
        ? "I could not find a call price in this result."
        : `With these inputs the call is worth about ${call.toFixed(2)} per share.\n\n` +
          "Someone thinking of buying it would compare that with the market price.";
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
