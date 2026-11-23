// A stand-in for the Claude Messages API (api.anthropic.com/v1/messages), for
// e2e tests only. Playwright starts it and points the compute service at it with
// AI_BASE_URL, so the real Claude client runs end to end without the
// network or a real key.
//
// AI Explain (no tools): it answers deterministically from the result JSON in the
// prompt. For a single-option result it quotes the call price the compute service
// calculated, and mentions buying so the not-advice notice shows. For any other
// tool it names the tool, counts the metrics computed, and says so when the result
// is demo data.
//
// AI Analyst (a tool-use conversation): the first turn calls options_price with
// the default inputs; once the tool result comes back it answers, citing the call
// price as [[value|calculation_id|call_price]]. A question containing "misquote"
// makes it cite 12.00 instead, so the UI's mismatch highlighting can be tested.

import { createServer } from "node:http";

const PORT = Number(process.env.ANTHROPIC_PORT || 9600);

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

const OPTION = {
  spot: 100,
  strike: 100,
  time_to_expiry: 1,
  volatility: 0.2,
  risk_free_rate: 0.05,
  dividend_yield: 0,
  option_type: "call",
};

function message(body, content, stopReason, inputLength) {
  return {
    id: "msg_fake",
    type: "message",
    role: "assistant",
    model: body.model,
    content,
    stop_reason: stopReason,
    usage: {
      input_tokens: Math.ceil(inputLength / 4),
      output_tokens: Math.ceil(JSON.stringify(content).length / 4),
    },
  };
}

function analystTurn(body) {
  const messages = body.messages;
  const question = typeof messages[0].content === "string" ? messages[0].content : "";
  const last = messages[messages.length - 1];
  const inputLength = JSON.stringify(messages).length;
  const results = Array.isArray(last.content) ? last.content.filter((b) => b.type === "tool_result") : [];
  if (results.length === 0 && body.tools && body.tool_choice?.type !== "none") {
    const call = { type: "tool_use", id: "toolu_fake_1", name: "options_price", input: OPTION };
    return message(body, [call], "tool_use", inputLength);
  }
  const result = results.length ? JSON.parse(results[results.length - 1].content) : null;
  const value = result?.metrics?.call_price?.value;
  if (value == null) {
    return message(body, [{ type: "text", text: "I could not price the option." }], "end_turn", inputLength);
  }
  const written = /misquote/i.test(question) ? "12.00" : value.toFixed(2);
  const text =
    `An at-the-money one-year call with these inputs is worth [[${written}|${result.calculation_id}|call_price]] per share.\n\n` +
    "That figure comes from the Black-Scholes model in the Options Calculator.";
  return message(body, [{ type: "text", text }], "end_turn", inputLength);
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
    if (body.tools || body.messages?.length > 1) return send(res, 200, analystTurn(body));
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
