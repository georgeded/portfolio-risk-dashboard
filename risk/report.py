import math
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from risk import config, data, metrics, signals, stress


class InputError(Exception):
    pass


def currency_code(code, field="base_currency") -> str:
    c = str(code or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", c):
        raise InputError(f"{field} must be a three letter currency code, got {code!r}")
    return c


def _number(value, field, ticker) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise InputError(f"{field} for {ticker} is not a number") from None
    if not math.isfinite(x):
        raise InputError(f"{field} for {ticker} is not a finite number")
    return x


def position_tickers(positions: list[dict]) -> list[str]:
    if not positions:
        raise InputError("At least one position is required")
    try:
        tickers = [data.normalize_ticker(p["ticker"]) for p in positions]
    except data.DataError as e:
        raise InputError(str(e)) from None
    if len(set(tickers)) != len(tickers):
        raise InputError("Duplicate tickers")
    return tickers


def resolve_positions(positions: list[dict], portfolio_value: float | None,
                      last_prices: pd.Series | None = None):
    """Turn the request positions into normalized weights and a portfolio value.

    Positions carry either a weight or a quantity, never a mix. Weights are
    scaled so their absolute values sum to one, so a short is a negative weight.
    With quantities the value comes from `last_prices`, in the base currency.
    """
    tickers = position_tickers(positions)
    has_w = [p.get("weight") is not None for p in positions]
    has_q = [p.get("quantity") is not None for p in positions]
    if any(has_w) and any(has_q):
        raise InputError("Use either weights or quantities, not both")

    if any(has_q):
        if not all(has_q):
            raise InputError("Every position needs a quantity")
        quantities = [_number(p["quantity"], "quantity", t) for p, t in zip(positions, tickers)]
        values = np.array([q * float(last_prices[t]) for q, t in zip(quantities, tickers)])
        gross = np.abs(values).sum()
        if gross == 0:
            raise InputError("Quantities sum to zero")
        weights = values / gross
        if portfolio_value is None:
            portfolio_value = float(gross)
    elif any(has_w):
        if not all(has_w):
            raise InputError("Every position needs a weight")
        raw = np.array([_number(p["weight"], "weight", t) for p, t in zip(positions, tickers)])
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
        quoted = p.get("currency") or info["currency"]
        if p.get("currency") and not re.fullmatch(r"[A-Za-z]{3}", str(p["currency"])):
            raise InputError(f"currency for {t} must be a three letter code, got {p['currency']!r}")
        currency, scale = data.currency_unit(quoted)
        infos.append({
            "ticker": t,
            "name": p.get("name") or info["name"],
            "sector": p.get("sector") or info["sector"] or "Unknown",
            "currency": currency,
            "price_scale": scale,
        })
    return infos


def _sector_weights(infos, weights):
    by_sector: dict[str, dict] = {}
    for info, w in zip(infos, weights):
        s = by_sector.setdefault(info["sector"], {"sector": info["sector"], "weight": 0.0, "positions": []})
        s["weight"] += abs(float(w))
        s["positions"].append(info["ticker"])
    return sorted(by_sector.values(), key=lambda s: -s["weight"])


def _to_base(prices: pd.DataFrame, units: dict, base: str) -> pd.DataFrame:
    """Prices of the given tickers converted to the base currency.

    `units` maps a ticker to its (currency, price scale).
    """
    out = {}
    for t, (currency, scale) in units.items():
        fx = 1.0 if currency == base else prices[data.fx_ticker(currency, base)]
        out[t] = prices[t] * scale * fx
    return pd.DataFrame(out, index=prices.index)


def _series(dates, port, bench):
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in dates],
        "portfolio": [float(v) for v in (1 + port).cumprod()],
        "benchmark": [float(v) for v in (1 + bench).cumprod()],
        "drawdown": [float(v) for v in metrics.drawdown_series(port)],
    }


def _round(obj, digits=6):
    if isinstance(obj, float):
        return round(obj, digits)
    if isinstance(obj, dict):
        return {k: _round(v, digits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v, digits) for v in obj]
    return obj


def build_report(positions: list[dict], benchmark: str = config.DEFAULT_BENCHMARK,
                 lookback_days: int = config.DEFAULT_LOOKBACK_DAYS,
                 confidence: float = config.DEFAULT_CONFIDENCE,
                 portfolio_value: float | None = None,
                 base_currency: str = config.DEFAULT_BASE_CURRENCY,
                 risk_free_rate: float = config.DEFAULT_RISK_FREE_RATE) -> dict:
    lookback_days = int(min(max(lookback_days, config.MIN_LOOKBACK_DAYS), config.MAX_LOOKBACK_DAYS))
    base_currency = currency_code(base_currency)
    try:
        benchmark = data.normalize_ticker(benchmark)
    except data.DataError as e:
        raise InputError(str(e)) from None

    tickers = position_tickers(positions)
    infos = _enrich(positions, tickers)
    units = {i["ticker"]: (i["currency"], i["price_scale"]) for i in infos}
    units[benchmark] = data.currency_unit(data.ticker_info(benchmark)["currency"])

    fx_pairs = [data.fx_ticker(c, base_currency) for c, _ in units.values() if c != base_currency]
    needed = list(dict.fromkeys(tickers + [benchmark] + list(config.FACTORS.values()) + fx_pairs))
    prices = data.load_prices(needed, lookback_days)
    base_prices = _to_base(prices, units, base_currency)

    tickers, weights, portfolio_value = resolve_positions(positions, portfolio_value, base_prices.iloc[-1])
    sectors = _sector_weights(infos, weights)
    largest_sector = sectors[0]["sector"]
    sector_etf = config.SECTOR_ETFS.get(largest_sector)
    # The sector ETF depends on the weights, so it is loaded once they are known.
    if sector_etf and sector_etf not in prices:
        prices = data.load_prices(needed + [sector_etf], lookback_days)
        base_prices = _to_base(prices, units, base_currency)

    # Risk is measured in the base currency. The stress betas use local
    # returns, because the FX scenario adds the currency translation itself.
    rets = data.simple_returns(base_prices)
    local_rets = data.simple_returns(prices)
    asset_rets = rets[tickers]
    bench_rets = rets[benchmark]
    factor_rets = local_rets[list(config.FACTORS.values())].rename(columns={v: k for k, v in config.FACTORS.items()})
    sector_rets = local_rets[sector_etf] if sector_etf else None
    port_rets = pd.Series(asset_rets.values @ weights, index=asset_rets.index)
    start = prices.index[0]

    dd = metrics.max_drawdown(port_rets, start)
    bench_dd = metrics.max_drawdown(bench_rets, start)
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
        "largest_sector": {"sector": sectors[0]["sector"], "weight": sectors[0]["weight"]},
    })

    corr_matrix = asset_rets.corr().values
    n = len(tickers)
    pairs = [(tickers[i], tickers[j], float(corr_matrix[i, j])) for i in range(n) for j in range(i + 1, n)]
    corr = {
        "tickers": tickers,
        "matrix": [[float(v) for v in row] for row in corr_matrix],
        "average_pairwise": float(np.mean([p[2] for p in pairs])) if pairs else 1.0,
        "highest_pair": None,
        "lowest_pair": None,
    }
    if pairs:
        hi = max(pairs, key=lambda p: p[2])
        lo = min(pairs, key=lambda p: p[2])
        corr["highest_pair"] = {"a": hi[0], "b": hi[1], "value": hi[2]}
        corr["lowest_pair"] = {"a": lo[0], "b": lo[1], "value": lo[2]}

    rc = metrics.risk_contributions(weights, asset_rets.cov().values)
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
            "ticker": t,
            "name": info["name"],
            "sector": info["sector"],
            "currency": info["currency"],
            "weight": float(weights[i]),
            "value": float(weights[i] * portfolio_value) if portfolio_value else None,
            "last_price": float(prices[t].iloc[-1] * info["price_scale"]),
            "period_return": metrics.period_return(r),
            "annualized_return": metrics.annualized_return(r),
            "annualized_volatility": metrics.annualized_volatility(r),
            "max_drawdown": metrics.max_drawdown(r, start)["max_drawdown"],
            "beta": metrics.beta(r, bench_rets),
            "correlation_to_benchmark": metrics.correlation(r, bench_rets),
            "var_historical": metrics.var_historical(r, confidence),
            "risk_share": share_by_ticker[t],
        })

    stress_results, betas = stress.run_all(
        tickers, weights, local_rets[tickers], asset_rets, factor_rets, sector_rets,
        [info["currency"] for info in infos], base_currency, portfolio_value, largest_sector,
    )
    for row in position_rows:
        row["factor_betas"] = {k: float(v) for k, v in betas.loc[row["ticker"]].items()}

    meter = signals.risk_meter(
        summary["annualized_volatility"], summary["max_drawdown"], downside["cvar_historical"],
        conc["hhi"], corr["average_pairwise"],
    )
    warns = signals.warnings(summary, downside, conc, corr, contributions)

    return _round({
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
            "currencies": sorted({info["currency"] for info in infos}),
        },
        "summary": summary,
        "risk_meter": meter,
        "warnings": warns,
        "downside": downside,
        "concentration": conc,
        "correlation": corr,
        "risk_contribution": risk_contribution,
        "positions": position_rows,
        "stress_tests": stress_results,
        "series": _series(rets.index, port_rets, bench_rets),
    })
