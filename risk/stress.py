import math

import numpy as np
import pandas as pd

from risk import config
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
