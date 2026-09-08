import math

import numpy as np
import pandas as pd

import config
from risk import metrics


def factor_betas(asset_returns: pd.DataFrame, factor_returns: pd.DataFrame) -> pd.DataFrame:
    """Joint OLS of each asset on all factors. Rows are assets, columns are factors."""
    x = np.column_stack([np.ones(len(factor_returns)), factor_returns.values])
    coef, *_ = np.linalg.lstsq(x, asset_returns.values, rcond=None)
    return pd.DataFrame(coef[1:].T, index=asset_returns.columns, columns=factor_returns.columns)


def single_beta(asset_returns: pd.DataFrame, factor: pd.Series) -> pd.Series:
    var = factor.var(ddof=1)
    if var == 0:
        return pd.Series(0.0, index=asset_returns.columns)
    return asset_returns.apply(lambda col: col.cov(factor) / var)


def _position_rows(tickers, weights, moves):
    contributions = weights * moves
    losing = contributions[contributions < 0]
    gross_loss = float(losing.sum()) if len(losing) else 0.0
    rows = []
    for t, w, m, c in zip(tickers, weights, moves, contributions):
        share = float(c / gross_loss) if gross_loss < 0 and c < 0 else 0.0
        rows.append({
            "ticker": t,
            "weight": float(w),
            "move_pct": float(m),
            "loss_pct": float(c),
            "share_of_loss": share,
        })
    rows.sort(key=lambda r: r["loss_pct"])
    return rows, float(contributions.sum())


def run_factor_scenario(scenario, tickers, weights, betas: pd.DataFrame, sector_betas,
                        currencies, base_currency, portfolio_value):
    moves = np.zeros(len(tickers))
    applied = {}
    for factor, shock in scenario["shocks"].items():
        if factor == "sector":
            if sector_betas is None:
                continue
            moves += sector_betas.values * shock
        else:
            moves += betas[factor].values * shock
        applied[factor] = shock

    if scenario.get("translation") and "dollar" in scenario["shocks"]:
        shock = scenario["shocks"]["dollar"]
        for i, cur in enumerate(currencies):
            cur = (cur or "USD").upper()
            if base_currency == "USD" and cur != "USD":
                moves[i] -= shock
            elif base_currency != "USD" and cur == "USD":
                moves[i] += shock

    rows, total = _position_rows(tickers, weights, moves)
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "description": scenario["description"],
        "method": "factor",
        "shocks": applied,
        "portfolio_loss_pct": total,
        "portfolio_loss_value": total * portfolio_value if portfolio_value else None,
        "positions": rows,
    }


def run_correlation_scenario(scenario, tickers, weights, returns: pd.DataFrame, portfolio_value):
    """Push every pairwise correlation up to a floor, then take the parametric CVaR over the horizon."""
    floor = scenario["correlation_floor"]
    horizon = scenario.get("horizon_days", 10)
    confidence = scenario.get("confidence", 0.99)
    stds = returns.std(ddof=1).values
    means = returns.mean().values
    corr = returns.corr().values
    stressed_corr = metrics.stress_correlation(corr, floor)
    cov_base = metrics.cov_from_corr(corr, stds)
    cov_stressed = metrics.cov_from_corr(stressed_corr, stds)

    base = metrics.risk_contributions(weights, cov_base)
    stressed = metrics.risk_contributions(weights, cov_stressed)
    mean_p = float(weights @ means)
    base_tail = metrics.parametric_from_moments(mean_p, base["volatility"], confidence, horizon)
    stressed_tail = metrics.parametric_from_moments(mean_p, stressed["volatility"], confidence, horizon)
    total = stressed_tail["cvar"]

    rows = []
    for t, w, share in zip(tickers, weights, stressed["share"]):
        loss = total * share
        rows.append({
            "ticker": t,
            "weight": float(w),
            "move_pct": float(loss / w) if w else 0.0,
            "loss_pct": float(loss),
            "share_of_loss": float(share) if loss < 0 else 0.0,
        })
    rows.sort(key=lambda r: r["loss_pct"])

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "description": scenario["description"],
        "method": "correlation",
        "shocks": {"correlation_floor": floor, "horizon_days": horizon, "confidence": confidence},
        "portfolio_loss_pct": float(total),
        "portfolio_loss_value": float(total * portfolio_value) if portfolio_value else None,
        "positions": rows,
        "details": {
            "volatility_before": base["volatility"] * math.sqrt(config.TRADING_DAYS),
            "volatility_after": stressed["volatility"] * math.sqrt(config.TRADING_DAYS),
            "average_correlation_before": _avg_offdiag(corr),
            "average_correlation_after": _avg_offdiag(stressed_corr),
            "cvar_before": float(base_tail["cvar"]),
            "cvar_after": float(stressed_tail["cvar"]),
        },
    }


def _avg_offdiag(m: np.ndarray) -> float:
    n = m.shape[0]
    if n < 2:
        return 1.0
    return float((m.sum() - np.trace(m)) / (n * (n - 1)))


def run_all(tickers, weights, returns, factor_returns, sector_factor, currencies,
            base_currency, portfolio_value, largest_sector):
    betas = factor_betas(returns, factor_returns)
    sector_betas = single_beta(returns, sector_factor) if sector_factor is not None else None
    results = []
    for scenario in config.SCENARIOS:
        if "correlation_floor" in scenario:
            res = run_correlation_scenario(scenario, tickers, weights, returns, portfolio_value)
        else:
            res = run_factor_scenario(scenario, tickers, weights, betas, sector_betas,
                                      currencies, base_currency, portfolio_value)
            if "sector" in scenario["shocks"]:
                res["sector"] = largest_sector
                if sector_betas is None:
                    res["portfolio_loss_pct"] = None
                    res["portfolio_loss_value"] = None
                    res["positions"] = []
                    res["note"] = "No sector ETF mapped for the largest sector"
        results.append(res)
    return results, betas
