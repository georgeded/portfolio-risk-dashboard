# Methodology

All calculations use daily simple returns on adjusted closes over the chosen
window. The portfolio return on a day is the weighted sum of the position
returns with the entered weights, which is the same as rebalancing to those
weights every day. 252 trading days make a year.

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

The wealth path is the cumulative product of `1 + return`. Drawdown on a day
is wealth divided by the running maximum minus one. Maximum drawdown is the
lowest point of that path. The peak date is the last high before the trough
and the recovery date is the first day wealth gets back to that high.

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

## Risk contribution

With weights `w` and the daily covariance matrix `S`, portfolio volatility is
`sigma = sqrt(w' S w)`. The marginal contribution of position `i` is
`(S w)_i / sigma` and its contribution is `w_i` times that. Contributions add
up to `sigma` exactly and each share is contribution over `sigma`. A share
well above the weight means the position adds more risk than its size, a
negative share means it offsets risk.

## Concentration

HHI is the sum of squared weights. The effective number of positions is
`1 / HHI`, the number of equal weight positions that would give the same HHI.
Sector weights add the absolute weights of the positions in each sector.
Sectors come from Yahoo Finance unless given in the request.

## Risk meter

Five components are each scored 0 to 100 by linear interpolation between a
low and a high anchor and clipped at both ends:

| Component | Low anchor (0) | High anchor (100) | Weight |
| --- | --- | --- | --- |
| Annualized volatility | 10% | 40% | 0.30 |
| Max drawdown | 5% | 40% | 0.20 |
| Historical CVaR 95, one day | 1% | 5% | 0.20 |
| HHI | 0.05 | 0.35 | 0.15 |
| Average pairwise correlation | 0.20 | 0.80 | 0.15 |

The score is the weighted sum. Below 25 is Low, below 50 Moderate, below 75
High, otherwise Very High. The anchors and weights are in `config.RISK_METER`.

## Warnings

| Code | Level | Fires when |
| --- | --- | --- |
| `position_weight` | warning | Largest position above 15% |
| `top3_weight` | warning | Three largest positions above 50% |
| `sector_weight` | warning | Largest sector above 40% |
| `effective_positions` | warning | Effective positions below 5 |
| `volatility` | warning | Annualized volatility above 30% |
| `max_drawdown` | critical | Max drawdown worse than -20% |
| `cvar` | critical | Historical CVaR 95 worse than -3% a day |
| `correlation` | warning | Average pairwise correlation above 0.60 |
| `beta` | warning | Beta to the benchmark above 1.30 |
| `risk_vs_weight` | info | A position's risk share is more than twice its weight |

Thresholds are in `config.THRESHOLDS`.

## Stress tests

### Factor scenarios

Each position is regressed on three factor returns at once, the market
(`SPY`), long Treasuries (`TLT`) and the dollar (`UUP`), giving a beta to each
factor with the others held fixed. A scenario is a set of factor shocks and a
position's estimated move is the sum of beta times shock over the shocked
factors. The portfolio loss is the weighted sum of the position moves.

| Scenario | Shocks |
| --- | --- |
| Market crash | market -20% |
| Sharp interest rate move | long Treasuries -10%, roughly 100bp higher yields |
| Recession | market -30%, long Treasuries +10%, dollar +5% |
| Sector crash | the SPDR ETF of the portfolio's largest sector -25%, using a separate single factor beta to that ETF |
| Large FX move | dollar -10% |

The FX scenario also applies a translation effect. When the book is reported
in a currency other than USD, every USD quoted position loses the full 10% on
top of its dollar beta. When the book is in USD, positions quoted in other
currencies gain 10%.

### Correlations rising

Every pairwise correlation below 0.8 is raised to 0.8 and the diagonal stays
at 1. Position volatilities are unchanged, so this is a pure loss of
diversification. The stressed covariance gives a stressed portfolio
volatility, and the reported loss is the parametric CVaR at 99% over ten
trading days under that covariance. The share of the loss by position is the
risk contribution share under the stressed matrix.

### Share of the loss

For every scenario, `share_of_loss` divides a losing position's contribution
by the sum of all losing contributions. Positions that gain in the scenario
get a share of 0.

## Limits

Betas from one year of daily data move around, and a three factor regression
does not separate the factors perfectly when they are correlated. Historical
VaR only knows the days in the window. Sector betas are to an ETF, not to the
position's own industry. The scenarios are stylized and sized by hand in
`config.py`, change them to match the risks the desk cares about.
