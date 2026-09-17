# API reference

Base path is `/api`. Every endpoint returns JSON. Fractions are decimals, so
`0.25` means 25%. Losses, drawdowns and VaR are negative numbers. The
interactive version with schemas is served at `/docs` when the app runs.

## GET /api/health

```json
{"status": "ok", "price_source": "yahoo"}
```

`price_source` is `csv` when `PRICES_CSV` is set.

## GET /api/scenarios

The factor tickers, the sector ETF map and the scenario definitions from
`config.py`.

## GET /api/thresholds

The warning thresholds, the risk meter anchors and the level cut offs.

## GET /api/lookup/{ticker}

Name, sector, currency and last price for one ticker. 404 when there is no
price history.

```json
{"ticker": "MSFT", "name": "Microsoft Corporation", "sector": "Technology", "currency": "USD", "last_price": 493.78}
```

## POST /api/report

Request body:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `positions` | list | required | See below |
| `benchmark` | string | `SPY` | Ticker used for beta, correlation and the growth chart |
| `lookback_days` | int | 252 | Trading days in the window, 60 to 1250 |
| `confidence` | float | 0.95 | Confidence level for VaR and CVaR |
| `portfolio_value` | float | null | Value of the book. Turns percentages into money amounts. Derived from prices when quantities are given |
| `base_currency` | string | `USD` | Currency the book is reported in. Drives the FX translation in the FX scenario |
| `risk_free_rate` | float | 0 | Annual rate used in the Sharpe ratio |

Each position:

| Field | Type | Meaning |
| --- | --- | --- |
| `ticker` | string | Yahoo Finance symbol |
| `weight` | float | Share of the book on any scale. All weights are divided by the sum of their absolute values, so a negative weight is a short |
| `quantity` | float | Number of shares. Use weights or quantities, not both |
| `name` | string | Optional display name |
| `sector` | string | Optional. Overrides the Yahoo sector. Use Yahoo's names (Technology, Financial Services, Healthcare, Energy, Consumer Cyclical, Consumer Defensive, Industrials, Basic Materials, Utilities, Real Estate, Communication Services) so the sector crash scenario can find its ETF |
| `currency` | string | Optional quote currency, default USD |

Errors come back as 400 with a `detail` string: unknown ticker, duplicate
tickers, mixed weights and quantities, too little overlapping history.

## GET /api/report

Same report, for quick tests in a browser.

```
/api/report?tickers=AAPL,MSFT&weights=60,40&benchmark=SPY&lookback_days=252&portfolio_value=100000&base_currency=USD
```

## Response

Top level keys, in the order a dashboard would read them.

### `as_of`, `generated_at`, `window`, `portfolio`

```json
{
  "as_of": "2026-09-18",
  "generated_at": "2026-09-20T14:53:42Z",
  "window": {"start": "2025-09-18", "end": "2026-09-18", "trading_days": 252, "benchmark": "SPY",
             "factors": {"market": "SPY", "rates": "TLT", "dollar": "UUP"}, "sector_factor": "XLK"},
  "portfolio": {"value": 100000, "base_currency": "USD", "position_count": 6}
}
```

### `summary`

| Field | Meaning |
| --- | --- |
| `period_return` | Total return over the window |
| `annualized_return` | Compound annual growth rate over the window |
| `annualized_volatility` | Standard deviation of daily returns times the square root of 252 |
| `sharpe` | (annualized return minus risk free rate) divided by volatility. `null` when volatility is zero |
| `max_drawdown` | Largest peak to trough fall |
| `current_drawdown` | Distance from the last peak today |
| `drawdown_peak_date`, `drawdown_trough_date`, `drawdown_recovery_date` | Dates around the max drawdown. Recovery is `null` when the book has not made a new high since |
| `beta` | Slope of portfolio returns on benchmark returns |
| `correlation_to_benchmark` | Correlation of daily returns |
| `benchmark_period_return`, `benchmark_annualized_return`, `benchmark_annualized_volatility`, `benchmark_max_drawdown` | The same for the benchmark |

### `risk_meter`

```json
{"score": 21.1, "level": "Low",
 "components": [{"key": "volatility", "name": "Volatility", "value": 0.164, "score": 21.3, "weight": 0.3}, ...]}
```

`score` is 0 to 100. `level` is Low below 25, Moderate below 50, High below
75, Very High otherwise. Each component carries its raw value, its own 0 to
100 score and the weight it has in the blend.

### `warnings`

A list, sorted critical first, empty when nothing is crossed.

```json
{"level": "warning", "code": "sector_weight", "title": "Sector concentration",
 "message": "Technology is 75% of the book, above 40%.", "value": 0.75, "threshold": 0.4}
```

Levels are `critical`, `warning` and `info`. Codes: `position_weight`,
`top3_weight`, `sector_weight`, `effective_positions`, `volatility`,
`max_drawdown`, `cvar`, `correlation`, `beta`, `risk_vs_weight`.

### `downside`

| Field | Meaning |
| --- | --- |
| `confidence`, `horizon_days` | What the VaR figures refer to, one day |
| `var_historical`, `cvar_historical` | Empirical quantile of daily returns and the mean of the days beyond it |
| `var_parametric`, `cvar_parametric` | The same assuming normal returns |
| `var_99_historical`, `cvar_99_historical` | At 99% regardless of `confidence` |
| `*_value` | Each of the above times the portfolio value, present when a value is known |
| `worst_windows` | Worst 1, 5 and 20 day returns with their dates |

### `concentration`

```json
{"hhi": 0.185, "effective_positions": 5.4, "top1_weight": 0.25, "top3_weight": 0.65,
 "top_position": {"ticker": "AAPL", "weight": 0.25},
 "sectors": [{"sector": "Technology", "weight": 0.75, "positions": ["AAPL", "MSFT", "NVDA", "ASML"]}, ...],
 "largest_sector": {"sector": "Technology", "weight": 0.75}}
```

### `correlation`

```json
{"tickers": ["AAPL", "MSFT"], "matrix": [[1.0, 0.13], [0.13, 1.0]],
 "average_pairwise": 0.07,
 "highest_pair": {"a": "NVDA", "b": "ASML", "value": 0.51},
 "lowest_pair": {"a": "XOM", "b": "ASML", "value": -0.22}}
```

`matrix` is in the order of `tickers`.

### `risk_contribution`

```json
{"portfolio_volatility": 0.164,
 "positions": [{"ticker": "NVDA", "weight": 0.2, "volatility": 0.38, "marginal": 0.28,
                "contribution": 0.057, "share": 0.35}, ...]}
```

Sorted by share, largest first. `contribution` is annualized and the
contributions sum to `portfolio_volatility`. `share` sums to 1 and can be
negative for a position that lowers portfolio risk.

### `positions`

One row per position with `ticker`, `name`, `sector`, `currency`, `weight`,
`value`, `last_price`, `period_return`, `annualized_return`,
`annualized_volatility`, `max_drawdown`, `beta`, `correlation_to_benchmark`,
`var_historical`, `risk_share` and `factor_betas` (`market`, `rates`,
`dollar`).

### `stress_tests`

One entry per scenario in `config.SCENARIOS`, in that order.

```json
{"id": "market_crash", "name": "Market crash",
 "description": "The equity market falls 20% with rates and the dollar unchanged.",
 "method": "factor", "shocks": {"market": -0.2},
 "portfolio_loss_pct": -0.214, "portfolio_loss_value": -21404.0,
 "positions": [{"ticker": "NVDA", "weight": 0.2, "move_pct": -0.41, "loss_pct": -0.081, "share_of_loss": 0.37}, ...]}
```

`positions` is sorted worst first. `move_pct` is the estimated move of the
position itself, `loss_pct` is weight times move and the sum of `loss_pct`
equals `portfolio_loss_pct`. `share_of_loss` is the position's part of the
gross loss (the sum over losing positions), so the shares of the losers sum to
1 and gainers get 0.

The sector crash entry adds `sector`. When the largest sector has no ETF
mapped the loss is `null` and a `note` explains why.

The correlation scenario has `method: "correlation"` and a `details` object
with `volatility_before`, `volatility_after`, `average_correlation_before`,
`average_correlation_after`, `cvar_before` and `cvar_after`.

### `series`

Aligned arrays for charts, one point per trading day in the window.

```json
{"dates": ["2025-09-19", ...], "portfolio": [1.004, ...], "benchmark": [1.002, ...], "drawdown": [0.0, ...]}
```

`portfolio` and `benchmark` are growth of 1, `drawdown` is the distance from
the running peak.
