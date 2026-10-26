# Portfolio Risk Dashboard

[![Live demo](https://img.shields.io/badge/demo-live-ae1f19?logo=render&logoColor=white)](https://portfolio-risk-dashboard-3qb8.onrender.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](.python-version)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)](api/app.py)
[![pandas](https://img.shields.io/badge/pandas-2.x-150458?logo=pandas&logoColor=white)](requirements.txt)
[![NumPy](https://img.shields.io/badge/NumPy-1.26%2B-013243?logo=numpy&logoColor=white)](requirements.txt)
[![Chart.js](https://img.shields.io/badge/Chart.js-4-FF6384?logo=chartdotjs&logoColor=white)](frontend/dashboard.js)
[![Data](https://img.shields.io/badge/data-Yahoo%20Finance-6001D2)](risk/data.py)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)](tests)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Risk analysis for a stock portfolio. Give it tickers with weights or share
counts and it returns volatility, drawdown, VaR and CVaR, beta, concentration,
risk contribution by position, a correlation heatmap, a 0 to 100 risk meter,
threshold warnings and six stress scenarios. A FastAPI service computes the
report and a single page frontend draws it.

**Live demo:** https://portfolio-risk-dashboard-3qb8.onrender.com
(API reference at [/docs](https://portfolio-risk-dashboard-3qb8.onrender.com/docs)).
The demo runs on a free instance, so the first request after a quiet period
takes about a minute.

## Features

| Section | Contents |
| --- | --- |
| Risk meter | A score from 0 to 100 and a level from Low to Very High, blended from volatility, drawdown, CVaR, concentration and correlation |
| Overview | Annualized return and volatility, maximum drawdown with dates, Sharpe, beta and correlation to the benchmark, historical VaR and CVaR, worst day and worst 20 days |
| Warnings | Large single positions, top three or sector concentration, few effective positions, high volatility, deep drawdown, heavy tail, high correlation, high beta, positions carrying far more risk than their weight |
| Risk contribution | Each position's share of portfolio volatility next to its weight (Euler decomposition) |
| Correlation | Pairwise heatmap with the average and the most correlated pair |
| Growth and drawdown | Growth of 1 against the benchmark and the drawdown path |
| Concentration | HHI, effective number of positions, weights by position and by sector |
| Stress tests | Market crash, rate shock, recession, sector crash, FX move and a correlation spike, each with the loss and the positions behind it |
| Positions | Every number in one table |

The book is built in an editor: search for a company, set weights with a
slider or enter share counts, and see each position's share of the book as it
changes. Sample books are included and the last book is remembered.

Books in several currencies are measured in a chosen base currency with daily
FX rates. The method behind every number is in
[docs/methodology.md](docs/methodology.md).

## Project structure

```
api/app.py              FastAPI app: routes, request models, static frontend
risk/
  config.py             Defaults, factors, scenarios, thresholds, risk meter anchors
  data.py               Prices from Yahoo Finance or a CSV, ticker checks, cache
  metrics.py            Return, volatility, drawdown, beta, VaR, CVaR, risk contribution
  report.py             Builds the full report, including currency conversion
  signals.py            Risk meter and warnings
  stress.py             Factor betas and the stress scenarios
frontend/               index.html, dashboard.js, dashboard.css
cli.py                  Report on the command line
tests/                  pytest suite on synthetic prices, no network needed
examples/               Request bodies with weights and with quantities
docs/                   API reference, methodology, embedding guide
```

## Getting started

Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn api.app:app --reload
```

The dashboard runs at http://localhost:8000 and the interactive API reference
at http://localhost:8000/docs. Prices are downloaded from Yahoo Finance and
cached per ticker in `cache/` for 12 hours.

## Command line

```bash
python cli.py AAPL:25 MSFT:20 NVDA:20 JPM:15 XOM:10 ASML:10 --value 100000
python cli.py AAPL MSFT ASML.AS --currency EUR --lookback 504 --json > report.json
```

Weights can be on any scale and are normalized. Tickers without weights are
equally weighted.

## API

```bash
curl -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d @examples/weights.json
```

For a quick test in the browser:

```
GET /api/report?tickers=AAPL,MSFT,NVDA&weights=50,30,20&portfolio_value=100000
```

Positions can also be share counts, as in a broker export. The value of the
book then comes from the latest prices, converted to the base currency
([example](examples/quantities.json)). The full request and response are in
[docs/api.md](docs/api.md).

## Embedding

The frontend is one global, `RiskDashboard`, with no build step. It needs
Chart.js 4 and the element ids in `index.html`. Point
`RiskDashboard.init({ apiBase: 'https://your-api' })` at a running service, or
call `RiskDashboard.render(report)` with a report fetched elsewhere. See
[docs/embedding.md](docs/embedding.md).

## Configuration

Benchmark, lookback window, factor tickers, sector ETFs, scenario shocks,
warning thresholds and risk meter anchors are set in `risk/config.py`.

| Variable | Purpose |
| --- | --- |
| `PRICES_CSV` | CSV with a `Date` column and one column per ticker. Replaces Yahoo Finance, for offline use or a fixed dataset |
| `CACHE_DIR` | Where price and ticker caches are written, default `cache/` |
| `CACHE_TTL_HOURS` | How long cached prices are reused, default 12 |
| `ALLOWED_ORIGINS` | Comma separated CORS origins, default `*` |

## Deployment

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/georgeded/portfolio-risk-dashboard)

The live demo runs on Render from the included [blueprint](render.yaml). Any
host that runs a Python web process works with:

```bash
pip install -r requirements.txt
uvicorn api.app:app --host 0.0.0.0 --port $PORT
```

## Tests

```bash
pytest
```

The suite builds synthetic prices with market, rate, dollar and FX factors and
never touches the network.

## Limitations

Betas are regressions on daily returns over the chosen window and move with
it. Historical VaR only knows the days it has seen. FX conversion uses daily
closes, so it is approximate across exchanges that close at different times.
The stress scenarios are stylized shocks, not forecasts. The output is meant
to make a risk discussion concrete, not to serve as a limit system.

## License

MIT, see [LICENSE](LICENSE).
