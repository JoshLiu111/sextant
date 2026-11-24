// Copy for the Risk & Performance technical indicators and correlation heatmap
// (`messages.riskTechnical`). Kept in its own file so it merges cleanly with the
// other Risk & Performance sections; it is part of the same `Messages` shape.
export const riskTechnical = {
  heading: "Technical indicators",
  intro:
    "Overlay common indicators on one ticker's price. Each indicator is computed on history from before the start date, so it has a value from the first day shown.",
  select: "Indicator chart for",
  dateLabel: "Date",
  toggles: {
    sma: "SMA",
    ema: "EMA",
    bollinger: "Bollinger Bands",
    rsi: "RSI",
    macd: "MACD",
  },
  inputs: {
    sma_window: "SMA window (days)",
    ema_window: "EMA window (days)",
    bollinger_window: "Bollinger window (days)",
    bollinger_width: "Band width (std devs)",
    rsi_window: "RSI window (days)",
    macd_fast: "MACD fast window (days)",
    macd_slow: "MACD slow window (days)",
    macd_signal: "MACD signal window (days)",
  },
  series: {
    price: "Close",
    sma: "SMA",
    ema: "EMA",
    bollinger_upper: "Upper band",
    bollinger_middle: "Middle band",
    bollinger_lower: "Lower band",
    rsi: "RSI",
    macd: "MACD",
    macd_signal: "Signal",
    macd_histogram: "Histogram",
  },
  charts: {
    price: "Price chart: the close with the selected overlays for",
    rsi: "RSI panel: relative strength index (0 to 100) for",
    macd: "MACD panel: MACD line, signal line and histogram for",
  },
  explainers: {
    movingAverages: {
      name: "Moving averages",
      what: "A smoothed price. The simple moving average (SMA) is the plain average of the last N closes; the exponential moving average (EMA) weights recent closes more.",
      formula: String.raw`\begin{aligned} \text{SMA}_t &= \dfrac{1}{N}\sum_{i=0}^{N-1} P_{t-i} \\ \text{EMA}_t &= \alpha P_t + (1 - \alpha)\,\text{EMA}_{t-1} \\ \alpha &= \dfrac{2}{N + 1} \end{aligned}`,
      how: "P is the close. The EMA starts from the SMA of the first N closes and warms up over 3 × N days of earlier history.",
      read: "Price above a rising average suggests an uptrend, below a falling one a downtrend. A short average crossing a long one is a common trend signal. Averages lag the price: longer windows are smoother and slower.",
    },
    bollinger: {
      name: "Bollinger Bands",
      what: "An envelope around the moving average whose width follows recent volatility.",
      formula: String.raw`\text{Bands} = \text{SMA}_N \pm k\,\sigma_N`,
      how: "σ_N is the population standard deviation of the last N closes; the middle band is the SMA itself (default N = 20, k = 2).",
      read: "Wide bands mean volatile prices, narrow bands calm ones. A close outside a band is unusually far from its recent average; it is not a buy or sell signal by itself.",
    },
    rsi: {
      name: "RSI",
      what: "The relative strength index: how strong recent gains were compared with recent losses, on a 0 to 100 scale.",
      formula: String.raw`\begin{aligned} \text{RSI} &= 100 - \dfrac{100}{1 + \bar{G}/\bar{L}} \\ \bar{G}_t &= \dfrac{(N - 1)\,\bar{G}_{t-1} + G_t}{N} \end{aligned}`,
      how: "Wilder's RSI over N days (default 14). Ḡ and L̄ are the average gain and loss; they start as simple means of the first N daily changes, then update as above (L̄ likewise).",
      read: "Above 70 is commonly called overbought, below 30 oversold. 100 means only gains over the window, 0 only losses.",
    },
    macd: {
      name: "MACD",
      what: "Moving average convergence divergence: the gap between a fast and a slow exponential moving average, in price units.",
      formula: String.raw`\begin{aligned} \text{MACD} &= \text{EMA}_{\text{fast}} - \text{EMA}_{\text{slow}} \\ \text{Signal} &= \text{EMA}_{\text{signal}}(\text{MACD}) \\ \text{Histogram} &= \text{MACD} - \text{Signal} \end{aligned}`,
      how: "Defaults: a 12-day fast EMA, a 26-day slow EMA and a 9-day signal line.",
      read: "A positive MACD means the short-term trend is above the long-term one. The MACD line crossing above its signal line (histogram turning positive) is a common bullish signal, crossing below a bearish one.",
    },
  },
  heatmap: {
    heading: "Correlation heatmap",
    label: "Correlation matrix of daily returns for every pair in the selection, benchmark included",
    versus: "vs",
    explainer: {
      name: "Correlation heatmap",
      what: "How closely each pair of tickers moves together, from −1 (opposite) through 0 (unrelated) to +1 (in lockstep).",
      formula: String.raw`\rho = \dfrac{\operatorname{Cov}(r_A, r_B)}{\sigma_A\,\sigma_B}`,
      how: "Pearson correlation of simple daily total returns (dividends included) over the selected date range, on the dates both tickers traded.",
      read: "Blue cells move together, red cells move against each other. Holdings with low or negative correlation diversify each other; highly correlated ones (near +1) add little diversification.",
    },
  },
} as const;
