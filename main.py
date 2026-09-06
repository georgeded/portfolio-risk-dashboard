import argparse
import json
import sys

import config
from risk import data, report


def parse_positions(items: list[str]) -> list[dict]:
    """Accepts AAPL, AAPL:25 or AAPL=25."""
    out = []
    for item in items:
        ticker, _, weight = item.replace("=", ":").partition(":")
        pos = {"ticker": ticker}
        if weight:
            pos["weight"] = float(weight)
        out.append(pos)
    return out


def pct(x, d=1, signed=True):
    if x is None:
        return "n/a"
    return f"{x * 100:{'+' if signed else ''}.{d}f}%"


def print_report(rep: dict):
    s = rep["summary"]
    d = rep["downside"]
    print(f"As of {rep['as_of']}, {rep['window']['trading_days']} trading days, benchmark {s['benchmark']}")
    print()
    print(f"{'Return (ann.)':22}{pct(s['annualized_return']):>10}   {'Volatility (ann.)':22}{pct(s['annualized_volatility'], signed=False):>10}")
    sharpe = "n/a" if s["sharpe"] is None else f"{s['sharpe']:.2f}"
    print(f"{'Max drawdown':22}{pct(s['max_drawdown']):>10}   {'Sharpe':22}{sharpe:>10}")
    print(f"{'Beta':22}{s['beta']:>10.2f}   {'Correlation to bench':22}{s['correlation_to_benchmark']:>10.2f}")
    print(f"{'VaR 95 (1 day)':22}{pct(d['var_historical'], 2):>10}   {'CVaR 95 (1 day)':22}{pct(d['cvar_historical'], 2):>10}")
    print()
    print("Risk contribution")
    for p in rep["risk_contribution"]["positions"]:
        print(f"  {p['ticker']:8}weight {p['weight'] * 100:5.1f}%   risk share {p['share'] * 100:5.1f}%")
    print()
    c = rep["concentration"]
    print(f"Concentration: HHI {c['hhi']:.3f}, {c['effective_positions']:.1f} effective positions, "
          f"largest sector {c['largest_sector']['sector']} {c['largest_sector']['weight'] * 100:.0f}%")
    print(f"Average pairwise correlation {rep['correlation']['average_pairwise']:.2f}")


def main():
    ap = argparse.ArgumentParser(description="Portfolio risk report for a list of tickers.")
    ap.add_argument("positions", nargs="+", help="TICKER or TICKER:WEIGHT")
    ap.add_argument("--benchmark", default=config.DEFAULT_BENCHMARK)
    ap.add_argument("--lookback", type=int, default=config.DEFAULT_LOOKBACK_DAYS, help="trading days")
    ap.add_argument("--confidence", type=float, default=config.DEFAULT_CONFIDENCE)
    ap.add_argument("--value", type=float, default=None, help="portfolio value in the base currency")
    ap.add_argument("--currency", default=config.DEFAULT_BASE_CURRENCY, help="base currency of the book")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args()

    try:
        rep = report.build_report(
            parse_positions(args.positions),
            benchmark=args.benchmark,
            lookback_days=args.lookback,
            confidence=args.confidence,
            portfolio_value=args.value,
            base_currency=args.currency,
        )
    except (report.InputError, data.DataError) as e:
        sys.exit(f"error: {e}")

    if args.json:
        json.dump(rep, sys.stdout, indent=1)
        print()
    else:
        print_report(rep)


if __name__ == "__main__":
    main()
