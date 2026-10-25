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
`risk/config.py`.

## GET /api/thresholds

The warning thresholds, the risk meter anchors and the level cut offs.

## GET /api/search

Tickers matching a company name or symbol, used for suggestions while typing.
Futures and options are left out.

```
/api/search?q=shell
```

```json
{"results": [{"ticker": "SHEL", "name": "Shell plc", "exchange": "NYSE", "type": "equity"},
             {"ticker": "SHEL.L", "name": "SHELL PLC ORD EUR0.07", "exchange": "London", "type": "equity"}]}
```

## GET /api/lookup/{ticker}

Name, sector, currency and last price for one ticker. `base` (default `USD`)
adds the price converted to that currency. 400 for a malformed symbol or
currency, 404 when there is no price history.

```json
{"ticker": "SHEL.L", "name": "SHELL PLC ORD EUR0.07", "sector": "Energy", "currency": "GBP",
 "last_price": 40.72, "price_in_base": 54.49, "base_currency": "USD"}
```

`last_price` is in the main unit of the quote currency, so pence are shown as
pounds.

## POST /api/report

Request body:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `positions` | list | required | See below |
| `benchmark` | string | `SPY` | Ticker used for beta, correlation and the growth chart |
| `lookback_days` | int | 252 | Trading days in the window, 60 to 1250 |
| `confidence` | float | 0.95 | Confidence level for VaR and CVaR |
| `portfolio_value` | float | null | Value of the book. Turns percentages into money amounts. Derived from prices when quantities are given |
| `base_currency` | string | `USD` | Three letter code of the currency risk is measured in. Positions in other currencies are converted, see [methodology](methodology.md#currencies) |
| `risk_free_rate` | float | 0 | Annual rate used in the Sharpe ratio |

Each position:

| Field | Type | Meaning |
| --- | --- | --- |
| `ticker` | string | Yahoo Finance symbol, for example `AAPL`, `BRK-B`, `ASML.AS` |
| `weight` | float | Share of the book on any scale. All weights are divided by the sum of their absolute values, so a negative weight is a short |
| `quantity` | float | Number of shares. Use weights or quantities, not both |
| `name` | string | Optional display name |
| `sector` | string | Optional. Overrides the Yahoo sector. Use Yahoo's names (Technology, Financial Services, Healthcare, Energy, Consumer Cyclical, Consumer Defensive, Industrials, Basic Materials, Utilities, Real Estate, Communication Services) so the sector crash scenario can find its ETF |
| `currency` | string | Optional quote currency, for example `EUR`, or `GBp` for prices in pence. Looked up from Yahoo when left out |

Errors come back as 400 with a `detail` string: malformed or unknown ticker,
duplicate tickers, mixed weights and quantities, a weight or quantity that is
not a finite number, a malformed currency code, a ticker with no recent prices,
too little overlapping history.

## GET /api/report

Same report, for quick tests in a browser. `weights` must be comma separated
numbers in the order of `tickers`.

```
/api/report?tickers=AAPL,MSFT&weights=60,40&benchmark=SPY&lookback_days=252&portfolio_value=100000&base_currency=USD
```
