# Sextant

A public suite of finance tools: options calculator, risk & performance, portfolio tracker, company health check, valuation, macro dashboard, screener & calendar, and an AI analyst whose numbers are traceable to deterministic calculations.

Inspired by [FinanceToolkit](https://github.com/JerBouma/FinanceToolkit). Not investment advice.

Status: planning. See [`docs/specs/01-sextant.md`](docs/specs/01-sextant.md).

## Development

Monorepo with two services deployed together to one Vercel project (see `vercel.json`):

- `apps/web`: Next.js (App Router) frontend
- `apps/compute`: Python FastAPI compute service, all routes under `/api/compute`

Requires Node 22+, Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
# compute service on :8000
cd apps/compute && uv sync && uv run uvicorn main:app --reload --port 8000
# frontend on :3000 (proxies /api/compute to :8000)
cd apps/web && npm install && npm run dev

# tests
cd apps/compute && uv run pytest
cd apps/web && npx playwright install chromium && npm run test:e2e
```

Environment variables are listed by name in `.env.example`. Never commit values.
