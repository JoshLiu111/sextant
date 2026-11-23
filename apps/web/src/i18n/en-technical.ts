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
      how: "SMA = mean of the last N closes. EMA = α × close + (1 − α) × yesterday's EMA, with α = 2 / (N + 1), started from the SMA of the first N closes and warmed up over 3 × N days of earlier history.",
      read: "Price above a rising average suggests an uptrend, below a falling one a downtrend. A short average crossing a long one is a common trend signal. Averages lag the price: longer windows are smoother and slower.",
    },
    bollinger: {
      name: "Bollinger Bands",
      what: "An envelope around the moving average whose width follows recent volatility.",
      how: "Middle band = N-day SMA. Upper and lower bands = middle ± k × the population standard deviation of the last N closes (default N = 20, k = 2).",
      read: "Wide bands mean volatile prices, narrow bands calm ones. A close outside a band is unusually far from its recent average; it is not a buy or sell signal by itself.",
    },
    rsi: {
      name: "RSI",
      what: "The relative strength index: how strong recent gains were compared with recent losses, on a 0 to 100 scale.",
      how: "Wilder's RSI = 100 − 100 / (1 + average gain / average loss) over N days (default 14). The averages start as simple means of the first N daily changes, then update as (previous × (N − 1) + today) / N.",
      read: "Above 70 is commonly called overbought, below 30 oversold. 100 means only gains over the window, 0 only losses.",
    },
    macd: {
      name: "MACD",
      what: "Moving average convergence divergence: the gap between a fast and a slow exponential moving average, in price units.",
      how: "MACD line = EMA(fast) − EMA(slow) (default 12 and 26 days). Signal line = EMA of the MACD line (default 9 days). Histogram = MACD line − signal line.",
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
      how: "Pearson correlation of simple daily total returns (dividends included) over the selected date range, on the dates both tickers traded.",
      read: "Blue cells move together, red cells move against each other. Holdings with low or negative correlation diversify each other; highly correlated ones (near +1) add little diversification.",
    },
  },
} as const;
