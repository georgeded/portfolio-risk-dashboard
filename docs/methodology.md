# Methodology

All calculations use daily simple returns on adjusted closes over the chosen
window. The portfolio return on a day is the weighted sum of the position
returns with the entered weights, which is the same as rebalancing to those
weights every day. 252 trading days make a year.

## Prices and calendars

Tickers on different exchanges trade on different days. Gaps of up to five
trading days are filled forward so the series line up, and days where a ticker
is still missing are dropped. A ticker with no price for longer than that, for
example after a delisting, is rejected with its last price date. Dropping its
missing days instead would quietly end the whole window on the day it stopped
trading.

## Currencies

Risk is measured in the base currency of the request. Each position's quote
currency comes from Yahoo Finance or from the request. Prices quoted in minor
units (London in pence, `GBp`) are scaled to the main unit. A position quoted
in another currency is converted with the daily Yahoo FX rate, so its return
in the base currency is `(1 + local return) * (1 + FX return) - 1`. The
benchmark is converted the same way. Quantities are valued at the latest price
times the latest rate.

## Weights

Weights are divided by the sum of their absolute values. `25, 20, 5` and
`0.5, 0.4, 0.1` give the same book. A negative weight is a short position.
When quantities are given instead, each position's value is quantity times the
latest price and weights follow from those values.

## Return and volatility

Period return is the compounded return over the window. Annualized return is
the compound annual growth rate, `(1 + period return) ^ (252 / days) - 1`.
Annualized volatility is the standard deviation of daily returns times
`sqrt(252)`. Sharpe is annualized return minus the risk free rate, divided by
annualized volatility.

## Maximum drawdown

The wealth path starts at 1 on the close before the first return and is the
cumulative product of `1 + return` after that. Drawdown on a day is wealth
divided by the running maximum, including that starting value, minus one, so a
fall that begins on the first day of the window counts in full. Maximum
drawdown is the lowest point of that path. The peak date is the last high
before the trough, or the start of the window when the book never rose above
its starting value. The recovery date is the first day wealth gets back to
that high.

## Beta and correlation

Beta is the covariance of portfolio and benchmark returns divided by the
benchmark variance. Correlation is the Pearson correlation of daily returns.
The correlation matrix uses the same daily returns for every pair.

## Value at risk

Historical VaR at 95% is the 5th percentile of daily portfolio returns.
Historical CVaR is the mean of the days at or below that percentile.
Parametric VaR and CVaR assume normal returns with the sample mean and
standard deviation:

```
VaR  = mean + std * z
CVaR = mean - std * pdf(z) / (1 - confidence)
```

with `z` the normal quantile at `1 - confidence`. Money amounts are the
fraction times the portfolio value.
