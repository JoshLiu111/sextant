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
  common: {
    explainer: {
      about: "About",
      what: "What it is",
      how: "How it's computed",
      read: "How to read it",
    },
    status: {
      pending: "Calculating…",
      missing_data: "Missing data",
      error: "Can't compute",
    },
    units: {
      currency: "",
      decimal: "",
      per_dollar: "per $1 move in spot",
      per_vol_point: "per 1 volatility point",
      per_day: "per calendar day",
      per_rate_point: "per 1 percentage point",
      ratio: "",
    } as Record<string, string>,
    errors: {
      heading: "Something went wrong",
      computeUnavailable: "The calculation service is unavailable right now. Please try again in a moment.",
      sourceUnavailable: "Data source temporarily unavailable, please retry.",
      invalidHeading: "Check your inputs",
    },
    demo: {
      badge: "Demo data",
      body: "These results use synthetic prices for fictional tickers, not real market data.",
    },
    calculation: {
      id: "Calculation",
      source: "Source",
      computedAt: "Computed",
    },
  },
  options: {
    intro:
      "European options priced with Black-Scholes(-Merton). Change any input and the results update.",
    inputsHeading: "Inputs",
    submit: "Calculate",
    inputs: {
      spot: { label: "Spot price", hint: "Current price of the underlying." },
      strike: { label: "Strike price", hint: "Price at which the option can be exercised." },
      time_to_expiry: { label: "Time to expiry (years)", hint: "For example 0.25 for three months." },
      volatility: { label: "Volatility (%)", hint: "Annualized, for example 20." },
      risk_free_rate: { label: "Risk-free rate (%)", hint: "Annualized, continuously compounded." },
      dividend_yield: { label: "Dividend yield (%)", hint: "Annualized, continuous. 0 if none." },
      option_type: { label: "Option type", hint: "Used for implied volatility and the chart." },
      market_price: { label: "Market price", hint: "Optional. Solves for implied volatility." },
    },
    optionTypes: { call: "Call", put: "Put" },
    sections: {
      prices: "Prices",
      greeks: "Greeks",
      iv: "Implied volatility",
      chart: "Payoff at expiry and value today",
    },
    chart: {
      label: "Chart of the option's payoff at expiry and its theoretical value today across spot prices",
      x: "Spot",
      payoff: "Payoff at expiry",
      value: "Value today",
      strike: "Strike",
      spot: "Spot",
    },
    metrics: {
      call_price: {
        name: "Call price",
        what: "The fair value today of a European call: the right to buy the underlying at the strike on the expiry date.",
        how: "Black-Scholes-Merton: S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2), with d1 = [ln(S/K) + (r − q + σ²/2)T] / (σ√T) and d2 = d1 − σ√T.",
        read: "What the option is worth under the model's assumptions (constant volatility, no early exercise). Compare it with the market price: higher market prices imply higher volatility.",
      },
      put_price: {
        name: "Put price",
        what: "The fair value today of a European put: the right to sell the underlying at the strike on the expiry date.",
        how: "Black-Scholes-Merton: K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1). Call and put satisfy put-call parity: C − P = S·e^(−qT) − K·e^(−rT).",
        read: "What the put is worth under the model. A put gains value as the spot falls or volatility rises.",
      },
      delta: {
        name: "Delta",
        what: "How much the option price changes for a $1 move in the underlying.",
        how: "Call: e^(−qT)·N(d1). Put: −e^(−qT)·N(−d1). Unit: per $1 move in spot.",
        read: "A call delta of 0.60 means the call gains about $0.60 if the spot rises $1. Call deltas run 0 to 1, put deltas −1 to 0. Roughly, |delta| is also the chance the option ends in the money.",
      },
      gamma: {
        name: "Gamma",
        what: "How fast delta changes for a $1 move in the underlying. The same for calls and puts.",
        how: "e^(−qT)·φ(d1) / (S·σ·√T), where φ is the standard normal density. Unit: change in delta per $1 move in spot.",
        read: "High gamma means delta (and so your exposure) shifts quickly. It peaks for at-the-money options close to expiry.",
      },
      vega: {
        name: "Vega",
        what: "How much the option price changes when volatility moves by 1 volatility point (for example from 20% to 21%). The same for calls and puts.",
        how: "S·e^(−qT)·φ(d1)·√T, divided by 100 so it is per 1 volatility point rather than per 100%.",
        read: "A vega of 0.38 means the option gains about $0.38 if implied volatility rises from 20% to 21%. Long options always have positive vega.",
      },
      theta: {
        name: "Theta",
        what: "How much the option price changes as one calendar day passes, all else equal (time decay).",
        how: "The derivative of the Black-Scholes price with respect to time, divided by 365 so it is per calendar day.",
        read: "A theta of −0.018 means the option loses about $0.018 of value per day. It is usually negative for long options and grows in size near expiry.",
      },
      rho: {
        name: "Rho",
        what: "How much the option price changes when the risk-free rate moves by 1 percentage point (for example from 5% to 6%).",
        how: "Call: K·T·e^(−rT)·N(d2). Put: −K·T·e^(−rT)·N(−d2). Divided by 100 so it is per 1 percentage point.",
        read: "Calls gain from higher rates (positive rho), puts lose (negative rho). Rho matters most for long-dated options.",
      },
      implied_volatility: {
        name: "Implied volatility",
        what: "The volatility that makes the Black-Scholes price equal the market price you entered, for the chosen option type.",
        how: "Solved numerically by bisection between 0.0001% and 500%. There is no solution if the price is at or below the discounted intrinsic value, or at or above the no-arbitrage upper bound.",
        read: "Compare it with the volatility you expect: if implied volatility is above your view, the option looks expensive; below it, cheap.",
      },
    },
  },
  risk: {
    intro:
      "Compare the return, volatility, worst fall, tail risk and risk-adjusted return of a few tickers against a benchmark over a date range. Change any input and the results update.",
    inputsHeading: "Inputs",
    submit: "Calculate",
    inputs: {
      tickers: { label: "Tickers", hint: "Comma-separated. Demo tickers: DEMO-A to DEMO-F." },
      benchmark: { label: "Benchmark", hint: "Demo benchmark: DEMO-MKT." },
      start: { label: "Start date", hint: "Demo data covers 2016-01-04 to 2025-12-31." },
      end: { label: "End date", hint: "Must be after the start date." },
      confidence: { label: "VaR confidence level (%)", hint: "For VaR and CVaR. 50 to 99.9; 95 is common." },
      risk_free_rate: {
        label: "Risk-free rate (%)",
        hint: "Annual, effective. For Sharpe and Sortino. 0 compares returns with cash earning nothing.",
      },
    },
    benchmarkSuffix: "(benchmark)",
    sections: {
      metrics: "Return and risk",
      chart: "Underwater chart",
    },
    chart: {
      select: "Underwater chart for",
      label: "Underwater chart: the fall from the previous high over time, for the selected ticker and the benchmark",
      x: "Date",
      peak: "Max drawdown start",
      trough: "Max drawdown end",
      window: "Max drawdown",
      from: "from",
      to: "to",
      recovered: "recovered",
      notRecovered: "not recovered by the end of the range",
    },
    metrics: {
      annualized_return: {
        name: "Annualized return",
        what: "The average yearly growth rate over the date range, with dividends reinvested (compound annual growth rate).",
        how: "Daily total return r = (close + dividend) / previous close − 1. Annualized return = (∏(1 + r))^(252 / n) − 1, where n is the number of daily returns and 252 trading days make a year.",
        read: "10% means the investment grew as if it earned 10% every year, compounded. It says nothing about how bumpy the ride was; compare it with volatility and max drawdown.",
      },
      annualized_volatility: {
        name: "Annualized volatility",
        what: "How much daily returns swing around their average, scaled to a year.",
        how: "Sample standard deviation of daily total returns (n − 1 in the denominator) × √252.",
        read: "Higher means a bumpier ride. As a rough guide, broad stock markets run around 15–20% a year; a single growth stock can exceed 40%.",
      },
      max_drawdown: {
        name: "Max drawdown",
        what: "The largest fall from a previous high to a later low within the date range, with dividends reinvested.",
        how: "Wealth W starts at 1 and grows by each daily total return. Drawdown = W / running peak of W − 1. Max drawdown is the size of the most negative drawdown, shown as a positive percentage; its start is the last high before the low and its end is the low.",
        read: "A max drawdown of 45% means that at the worst moment the investment was worth 45% less than at its prior peak. A 45% fall needs an 82% gain to get back. The underwater chart shows when it happened.",
      },
      var: {
        name: "Historical VaR (1 day)",
        what: "Value at Risk: a one-day loss that was exceeded only on the worst (100 − confidence)% of days in the date range.",
        how: "Sort the n daily total returns from worst to best and take the k-th worst, where k = ⌈n × (1 − confidence)⌉ (no interpolation). VaR is that return with the sign flipped, so a loss shows as a positive percentage. It needs at least 1 / (1 − confidence) returns, for example 100 at 99%.",
        read: "A 95% VaR of 3% means that on 95% of days in the range the investment lost less than 3%. It is not the worst case: it says nothing about how bad the other 5% of days were (see CVaR). A higher confidence level gives a larger VaR.",
      },
      cvar: {
        name: "Historical CVaR (1 day)",
        what: "Conditional VaR, also called expected shortfall: the average one-day loss on the days at or beyond the VaR.",
        how: "The mean of the k worst daily total returns (the same k as VaR), with the sign flipped so a loss is positive.",
        read: "A 95% CVaR of 4.5% means that on the worst 5% of days the investment lost 4.5% on average. CVaR is always at least as large as VaR; a big gap means a fat tail with rare, severe losses.",
      },
      sharpe: {
        name: "Sharpe ratio",
        what: "Return in excess of the risk-free rate per unit of total volatility, annualized.",
        how: "Daily excess return e = r − rf_daily, with rf_daily = (1 + annual risk-free rate)^(1/252) − 1. Sharpe = mean(e) / standard deviation of e (n − 1) × √252. Unit: a ratio, no unit.",
        read: "Higher is better. Around 0.5 is typical for a broad stock market over long periods, above 1 is strong. A negative Sharpe means the investment earned less than the risk-free rate.",
      },
      sortino: {
        name: "Sortino ratio",
        what: "Like Sharpe, but it only counts downside volatility: returns below the risk-free rate.",
        how: "Same daily excess return e as Sharpe. Downside deviation = √(mean of min(e, 0)²) over all days. Sortino = mean(e) / downside deviation × √252. Unit: a ratio, no unit.",
        read: "Higher is better. It is usually larger than Sharpe because upside swings are not penalized. A Sortino far above the Sharpe means the volatility was mostly on the upside.",
      },
      beta: {
        name: "Beta vs benchmark",
        what: "How much the ticker tends to move when the benchmark moves.",
        how: "Covariance of the ticker's and the benchmark's daily total returns divided by the variance of the benchmark's returns, on the days both have data (raw returns, not excess). Unit: a ratio, no unit. The benchmark's beta to itself is 1.",
        read: "1 means it moves with the benchmark; 1.4 means it tends to move 1.4% when the benchmark moves 1%; 0.2 means it barely follows it. Beta only captures the part of the risk that comes from the benchmark.",
      },
    },
  },
  portfolio: {
    intro:
      "Build a demo portfolio from tickers and weights, or load a classic allocation, and compare its cumulative return and risk with a benchmark. Change any input and the results update.",
    inputsHeading: "Inputs",
    submit: "Calculate",
    presets: {
      heading: "Presets",
      hint: "Classic allocations mapped onto demo tickers.",
      items: {
        sixtyForty: {
          name: "60/40",
          description: "60% stocks (DEMO-C, an index tracker), 40% bonds (DEMO-E, defensive and low beta).",
        },
        allWeather: {
          name: "All Weather",
          description:
            "30% stocks (DEMO-C), 55% long and intermediate bonds (DEMO-E), 7.5% gold (DEMO-A, low volatility), 7.5% commodities (DEMO-F, speculative).",
        },
      },
    },
    holdings: {
      heading: "Holdings",
      hint: "Demo tickers: DEMO-A to DEMO-F. Weights are a share of the portfolio and must add up to 100%. The portfolio is rebalanced to these weights every day.",
      ticker: "Ticker",
      weight: "Weight",
      weightUnit: "(%)",
      add: "Add holding",
      remove: "Remove holding",
      total: "Total",
    },
    inputs: {
      benchmark: { label: "Benchmark", hint: "Demo benchmark: DEMO-MKT." },
      start: { label: "Start date", hint: "Demo data covers 2016-01-04 to 2025-12-31." },
      end: { label: "End date", hint: "Must be after the start date." },
      confidence: { label: "VaR confidence level (%)", hint: "For VaR and CVaR. 50 to 99.9; 95 is common." },
      risk_free_rate: {
        label: "Risk-free rate (%)",
        hint: "Annual, effective. For Sharpe and Sortino.",
      },
    },
    portfolioLabel: "Portfolio",
    benchmarkSuffix: "(benchmark)",
    sections: {
      chart: "Cumulative return",
      metrics: "Portfolio risk",
      metricsNote:
        "The portfolio's daily return is the weighted sum of its holdings' daily total returns. These metrics are computed on that series with the same formulas as Risk & Performance.",
    },
    chart: {
      label: "Cumulative return of the portfolio and the benchmark over time, with dividends reinvested",
      x: "Date",
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
