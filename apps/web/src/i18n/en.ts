// All user-facing English strings. Keep UI copy here (not inline in components)
// so a second locale can be added later by providing another object of the
// same `Messages` shape.
export const en = {
  site: {
    name: "Sextant",
    tagline: "Free, transparent finance tools. Every number shows how it was computed.",
    menu: "Menu",
    toolsNavLabel: "Tools",
  },
  auth: {
    signIn: "Sign in with Google",
    signOut: "Sign out",
    account: "Account",
  },
  account: {
    heading: "Account",
    signedInAs: "Signed in as",
    signedOut: "You are not signed in. Every tool works without an account; sign in to save your work.",
    deleted: "Your account and all of its data were deleted.",
    errors: {
      signin: "Sign-in did not complete. Please try again.",
      unavailable: "Sign-in is not available right now.",
      delete: "Your account could not be deleted. Please try again.",
    },
    delete: {
      heading: "Delete account",
      body: "Permanently delete your account and everything saved under it. This cannot be undone.",
      button: "Delete account",
      confirm: "Yes, permanently delete my account",
      cancel: "Cancel",
      warning: "Are you sure? All of your data will be removed and you will be signed out.",
    },
  },
  home: {
    heading: "Finance tools",
    intro:
      "Pick a tool to get started. Every tool works without signing in and opens with sensible defaults.",
  },
  tools: {
    options: {
      name: "Options Calculator",
      description: "Price European options with Black-Scholes, see the Greeks, implied volatility and payoff.",
    },
    risk: {
      name: "Risk & Performance",
      description: "Compare return, volatility, drawdown, VaR, Sharpe and Beta for a few tickers against a benchmark.",
    },
    portfolio: {
      name: "My Portfolio",
      description: "Build a portfolio from tickers and weights and see its performance and risk versus a benchmark.",
    },
    company: {
      name: "Company Health Check",
      description: "Standardized financial statements, core ratios and Altman Z-Score from SEC filings.",
    },
    valuation: {
      name: "Valuation Calculator",
      description: "Discounted cash flow valuation with a WACC breakdown and a sensitivity table.",
    },
    macro: {
      name: "Macro Dashboard",
      description: "Key US economic indicators, the Treasury yield curve and the 10Y-2Y spread.",
    },
    screener: {
      name: "Screener & Calendar",
      description: "Screen US companies on fundamentals and follow the latest SEC filings.",
    },
    "ai-analyst": {
      name: "AI Analyst",
      description: "Ask questions in plain English and get answers backed by traceable calculations.",
    },
  },
  comingSoon: {
    badge: "Coming soon",
    body: "This tool is not built yet. Check back soon.",
    back: "Back to all tools",
  },
  compute: {
    label: "Compute service",
    online: "online",
    offline: "offline",
    checking: "checking…",
  },
  footer: {
    disclaimer:
      "Not investment advice. Sextant is for education and research only; results may be wrong or out of date.",
    sourcesLabel: "Data sources",
  },
  notFound: {
    heading: "Page not found",
    back: "Back to all tools",
  },
} as const;

export type Messages = typeof en;
