import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import config
from risk import data, metrics, signals, stress


class InputError(Exception):
    pass


def resolve_positions(positions: list[dict], portfolio_value: float | None):
    """Turn the request positions into normalized weights and a portfolio value.

    Positions carry either a weight or a quantity, never a mix. Weights are
    scaled so their absolute values sum to one, so a short is a negative weight.
    With quantities the value comes from the latest price.
    """
    if not positions:
        raise InputError("At least one position is required")
    tickers = [p["ticker"].strip().upper() for p in positions]
    if len(set(tickers)) != len(tickers):
        raise InputError("Duplicate tickers")

    has_w = [p.get("weight") is not None for p in positions]
    has_q = [p.get("quantity") is not None for p in positions]
    if any(has_w) and any(has_q):
        raise InputError("Use either weights or quantities, not both")

    if any(has_q):
        if not all(has_q):
            raise InputError("Every position needs a quantity")
        prices = data.last_prices(tickers)
        values = np.array([float(p["quantity"]) * float(prices[t]) for p, t in zip(positions, tickers)])
        gross = np.abs(values).sum()
        weights = values / gross
        if portfolio_value is None:
            portfolio_value = float(gross)
    elif any(has_w):
        if not all(has_w):
            raise InputError("Every position needs a weight")
        raw = np.array([float(p["weight"]) for p in positions])
        gross = np.abs(raw).sum()
        if gross == 0:
            raise InputError("Weights sum to zero")
        weights = raw / gross
    else:
        weights = np.full(len(tickers), 1 / len(tickers))

    return tickers, weights, portfolio_value


def _enrich(positions, tickers):
    infos = []
    for p, t in zip(positions, tickers):
        info = data.ticker_info(t)
        infos.append({
            "ticker": t,
            "name": p.get("name") or info["name"],
            "sector": p.get("sector") or info["sector"] or "Unknown",
            "currency": (p.get("currency") or info["currency"] or "USD").upper(),
        })
    return infos


def _sector_weights(infos, weights):
    by_sector: dict[str, dict] = {}
    for info, w in zip(infos, weights):
        s = by_sector.setdefault(info["sector"], {"sector": info["sector"], "weight": 0.0, "positions": []})
        s["weight"] += abs(float(w))
        s["positions"].append(info["ticker"])
    sectors = sorted(by_sector.values(), key=lambda s: -s["weight"])
    return sectors


def _series(dates, port, bench):
    port_wealth = (1 + port).cumprod()
    bench_wealth = (1 + bench).cumprod()
    dd = metrics.drawdown_series(port)
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in dates],
        "portfolio": [round(float(v), 6) for v in port_wealth],
        "benchmark": [round(float(v), 6) for v in bench_wealth],
        "drawdown": [round(float(v), 6) for v in dd],
    }


def build_report(positions: list[dict], benchmark: str = config.DEFAULT_BENCHMARK,
                 lookback_days: int = config.DEFAULT_LOOKBACK_DAYS,
                 confidence: float = config.DEFAULT_CONFIDENCE,
                 portfolio_value: float | None = None,
                 base_currency: str = config.DEFAULT_BASE_CURRENCY,
                 risk_free_rate: float = config.DEFAULT_RISK_FREE_RATE) -> dict:
    lookback_days = int(min(max(lookback_days, config.MIN_LOOKBACK_DAYS), config.MAX_LOOKBACK_DAYS))
    benchmark = benchmark.strip().upper()
    base_currency = base_currency.strip().upper()

    tickers, weights, portfolio_value = resolve_positions(positions, portfolio_value)
    infos = _enrich(positions, tickers)
    sectors = _sector_weights(infos, weights)
    largest_sector = sectors[0]["sector"] if sectors else None
    sector_etf = config.SECTOR_ETFS.get(largest_sector)

    needed = list(dict.fromkeys(tickers + [benchmark] + list(config.FACTORS.values())
                                + ([sector_etf] if sector_etf else [])))
    prices = data.load_prices(needed, lookback_days)
    rets = data.simple_returns(prices)

    asset_rets = rets[tickers]
    bench_rets = rets[benchmark]
    factor_rets = rets[list(config.FACTORS.values())].rename(columns={v: k for k, v in config.FACTORS.items()})
    sector_rets = rets[sector_etf] if sector_etf else None
    port_rets = pd.Series(asset_rets.values @ weights, index=asset_rets.index)

    dd = metrics.max_drawdown(port_rets)
    bench_dd = metrics.max_drawdown(bench_rets)
    summary = {
        "benchmark": benchmark,
        "period_return": metrics.period_return(port_rets),
        "annualized_return": metrics.annualized_return(port_rets),
        "annualized_volatility": metrics.annualized_volatility(port_rets),
        "sharpe": metrics.sharpe_ratio(port_rets, risk_free_rate),
        "max_drawdown": dd["max_drawdown"],
        "current_drawdown": dd["current_drawdown"],
        "drawdown_peak_date": dd["peak_date"],
        "drawdown_trough_date": dd["trough_date"],
        "drawdown_recovery_date": dd["recovery_date"],
        "beta": metrics.beta(port_rets, bench_rets),
        "correlation_to_benchmark": metrics.correlation(port_rets, bench_rets),
        "benchmark_period_return": metrics.period_return(bench_rets),
        "benchmark_annualized_return": metrics.annualized_return(bench_rets),
        "benchmark_annualized_volatility": metrics.annualized_volatility(bench_rets),
        "benchmark_max_drawdown": bench_dd["max_drawdown"],
    }

    downside = {
        "confidence": confidence,
        "horizon_days": 1,
        "var_historical": metrics.var_historical(port_rets, confidence),
        "cvar_historical": metrics.cvar_historical(port_rets, confidence),
        "var_parametric": metrics.var_parametric(port_rets, confidence),
        "cvar_parametric": metrics.cvar_parametric(port_rets, confidence),
        "var_99_historical": metrics.var_historical(port_rets, 0.99),
        "cvar_99_historical": metrics.cvar_historical(port_rets, 0.99),
        "worst_windows": metrics.worst_windows(port_rets),
    }
    if portfolio_value:
        for key in ("var_historical", "cvar_historical", "var_parametric", "cvar_parametric",
                    "var_99_historical", "cvar_99_historical"):
            downside[key + "_value"] = downside[key] * portfolio_value

    conc = metrics.concentration(weights)
    top_idx = int(np.argmax(np.abs(weights)))
    conc.update({
        "top_position": {"ticker": tickers[top_idx], "weight": float(abs(weights[top_idx]))},
        "sectors": sectors,
        "largest_sector": {"sector": sectors[0]["sector"], "weight": sectors[0]["weight"]} if sectors else None,
    })

    corr_matrix = asset_rets.corr().values
    n = len(tickers)
    pairs = [(tickers[i], tickers[j], float(corr_matrix[i, j])) for i in range(n) for j in range(i + 1, n)]
    corr = {
        "tickers": tickers,
        "matrix": [[round(float(v), 4) for v in row] for row in corr_matrix],
        "average_pairwise": float(np.mean([p[2] for p in pairs])) if pairs else 1.0,
        "highest_pair": None,
        "lowest_pair": None,
    }
    if pairs:
        hi = max(pairs, key=lambda p: p[2])
        lo = min(pairs, key=lambda p: p[2])
        corr["highest_pair"] = {"a": hi[0], "b": hi[1], "value": hi[2]}
        corr["lowest_pair"] = {"a": lo[0], "b": lo[1], "value": lo[2]}

    cov_daily = asset_rets.cov().values
    rc = metrics.risk_contributions(weights, cov_daily)
    ann = math.sqrt(config.TRADING_DAYS)
    contributions = []
    for i, t in enumerate(tickers):
        contributions.append({
            "ticker": t,
            "weight": float(weights[i]),
            "volatility": float(asset_rets[t].std(ddof=1) * ann),
            "marginal": float(rc["marginal"][i] * ann),
            "contribution": float(rc["contribution"][i] * ann),
            "share": float(rc["share"][i]),
        })
    contributions.sort(key=lambda r: -r["share"])
    risk_contribution = {
        "portfolio_volatility": float(rc["volatility"] * ann),
        "positions": contributions,
    }

    share_by_ticker = {r["ticker"]: r["share"] for r in contributions}
    position_rows = []
    for i, (t, info) in enumerate(zip(tickers, infos)):
        r = asset_rets[t]
        position_rows.append({
            **info,
            "weight": float(weights[i]),
            "value": float(weights[i] * portfolio_value) if portfolio_value else None,
            "last_price": float(prices[t].iloc[-1]),
            "period_return": metrics.period_return(r),
            "annualized_return": metrics.annualized_return(r),
            "annualized_volatility": metrics.annualized_volatility(r),
            "max_drawdown": metrics.max_drawdown(r)["max_drawdown"],
            "beta": metrics.beta(r, bench_rets),
            "correlation_to_benchmark": metrics.correlation(r, bench_rets),
            "var_historical": metrics.var_historical(r, confidence),
            "risk_share": share_by_ticker[t],
        })

    currencies = [info["currency"] for info in infos]
    stress_results, betas = stress.run_all(
        tickers, weights, asset_rets, factor_rets, sector_rets, currencies,
        base_currency, portfolio_value, largest_sector,
    )
    for row in position_rows:
        row["factor_betas"] = {k: float(v) for k, v in betas.loc[row["ticker"]].items()}

    meter = signals.risk_meter(
        summary["annualized_volatility"], summary["max_drawdown"], downside["cvar_historical"],
        conc["hhi"], corr["average_pairwise"],
    )

    return {
        "as_of": prices.index[-1].strftime("%Y-%m-%d"),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {
            "start": rets.index[0].strftime("%Y-%m-%d"),
            "end": rets.index[-1].strftime("%Y-%m-%d"),
            "trading_days": int(len(rets)),
            "benchmark": benchmark,
            "factors": config.FACTORS,
            "sector_factor": sector_etf,
        },
        "portfolio": {
            "value": portfolio_value,
            "base_currency": base_currency,
            "position_count": len(tickers),
        },
        "summary": summary,
        "risk_meter": meter,
        "downside": downside,
        "concentration": conc,
        "correlation": corr,
        "risk_contribution": risk_contribution,
        "positions": position_rows,
        "stress_tests": stress_results,
        "series": _series(rets.index, port_rets, bench_rets),
    }
