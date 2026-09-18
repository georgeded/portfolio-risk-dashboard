# Integration notes

The frontend is three files with no build step: `frontend/index.html`,
`frontend/dashboard.js` and `frontend/dashboard.css`. Everything on the page
is drawn from one JSON object, the response of `POST /api/report`, so a site
can either embed the page as is or reuse the script against its own markup.

## Run the API next to the site

Start the service with `uvicorn api.app:app --host 0.0.0.0 --port 8000` and
put it behind the site's reverse proxy at a path such as `/risk-api`. CORS is
open by default. To restrict it set `ALLOWED_ORIGINS` to the site origin.

The API is stateless. Requests take a few seconds the first time a ticker is
seen (a price download) and well under a second after that while the cache is
warm. Nothing is stored except the price cache in `cache/`.

## Embed the page

1. Include Chart.js 4 once on the page. The frontend was written against
   `chart.js@4.4.0`.
2. Include `dashboard.css` and `dashboard.js`.
3. Paste the markup inside `<div class="rd-shell">` from `index.html` into the
   tab or panel where the dashboard lives. Keep the element ids, the script
   looks them up by id.
4. Call `RiskDashboard.init({ apiBase: 'https://example.org/risk-api' })`.
   `apiBase` is prefixed to `/api/report`.

`init` wires the form and runs the default book. To skip the form and render
a fixed book, hide the form and call `load` directly:

```js
RiskDashboard.load({
  positions: [{ ticker: 'AAPL', weight: 25 }, { ticker: 'MSFT', weight: 20 }],
  benchmark: 'SPY',
  lookback_days: 252,
  portfolio_value: 100000,
  base_currency: 'USD'
})
```

`load` returns a promise with the report. `RiskDashboard.render(report)`
draws an object that was fetched elsewhere, for example server side.

## Feed it from live holdings

A broker position list usually has a symbol and a quantity. Send those as
`quantity` and the API prices them:

```js
const positions = holdings.map(h => ({ ticker: h.symbol, quantity: h.qty }))
RiskDashboard.load({ positions, base_currency: 'EUR' })
```

Pass `sector` when the site already knows it, that avoids a Yahoo lookup and
makes the sector crash scenario deterministic.

## Style

All classes start with `rd-` so nothing collides. The visual language is a
white card with an 18px radius, a red accent `#ae1f19`, ink `#111827`, grey
`#6b7280`, hairline borders `#eef0f2` and the Chivo typeface. If the host site
already has equivalent classes the mapping is direct:

| Dashboard class | Role |
| --- | --- |
| `rd-card` | white card with border and soft shadow |
| `rd-h`, `rd-h2`, `rd-sub` | page title, card title, grey subtitle |
| `rd-stats`, `rd-stat`, `rd-stat__l`, `rd-stat__v`, `rd-stat__n` | stat tile grid, tile, label, value, note |
| `rd-pill`, `rd-pill--grey`, `--green`, `--amber`, `--orange`, `--red` | small uppercase status pill |
| `rd-btn`, `rd-btn--primary`, `rd-btn--ghost` | buttons |
| `rd-table` | data table with right aligned numbers |
| `rd-wrow`, `rd-bar` | label, bar and percentage row used for weights |
| `rd-two`, `rd-two--wide` | two column card grid |

The charts use Chart.js with hairline grids, thin bars and the accent red for
the portfolio series and grey for the reference series. Colors are constants
at the top of `dashboard.js`.

## Building a different frontend

Everything a chart needs is in the response, precomputed:

| Widget | Fields |
| --- | --- |
| Risk meter | `risk_meter.score`, `risk_meter.level`, `risk_meter.components[]` |
| Stat tiles | `summary`, `downside` |
| Warnings | `warnings[]` with `level`, `title`, `message` |
| Risk contribution bars | `risk_contribution.positions[]`, `share` against `weight` |
| Heatmap | `correlation.tickers`, `correlation.matrix` |
| Growth and drawdown lines | `series.dates`, `series.portfolio`, `series.benchmark`, `series.drawdown` |
| Concentration | `concentration.sectors[]`, `positions[].weight`, `concentration.effective_positions` |
| Stress bars and cards | `stress_tests[]`, each with `portfolio_loss_pct`, `portfolio_loss_value`, `positions[]` |
| Table | `positions[]` |

The field by field description is in [api.md](api.md).
