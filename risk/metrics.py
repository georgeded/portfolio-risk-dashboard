import math

import numpy as np
import pandas as pd

from config import TRADING_DAYS


def period_return(r: pd.Series) -> float:
    return float(np.prod(1 + r.values) - 1)


def annualized_return(r: pd.Series) -> float:
    n = len(r)
    if n == 0:
        return 0.0
    growth = np.prod(1 + r.values)
    if growth <= 0:
        return -1.0
    return float(growth ** (TRADING_DAYS / n) - 1)


def annualized_volatility(r: pd.Series) -> float:
    if len(r) < 2:
        return 0.0
    return float(r.std(ddof=1) * math.sqrt(TRADING_DAYS))


def sharpe_ratio(r: pd.Series, risk_free_rate: float = 0.0) -> float | None:
    vol = annualized_volatility(r)
    if vol == 0:
        return None
    return (annualized_return(r) - risk_free_rate) / vol


def drawdown_series(r: pd.Series) -> pd.Series:
    wealth = (1 + r).cumprod()
    peak = wealth.cummax()
    return wealth / peak - 1


def max_drawdown(r: pd.Series) -> dict:
    """Largest peak to trough fall, with the dates around it and where we are now."""
    dd = drawdown_series(r)
    if dd.empty:
        return {"max_drawdown": 0.0, "current_drawdown": 0.0, "peak_date": None,
                "trough_date": None, "recovery_date": None}
    trough = dd.idxmin()
    wealth = (1 + r).cumprod()
    before = wealth.loc[:trough]
    peak = before.idxmax()
    after = wealth.loc[trough:]
    recovered = after[after >= wealth.loc[peak]]
    recovery = recovered.index[0] if len(recovered) and recovered.index[0] != trough else None
    return {
        "max_drawdown": float(dd.min()),
        "current_drawdown": float(dd.iloc[-1]),
        "peak_date": peak.strftime("%Y-%m-%d"),
        "trough_date": trough.strftime("%Y-%m-%d"),
        "recovery_date": recovery.strftime("%Y-%m-%d") if recovery is not None else None,
    }


def beta(r: pd.Series, market: pd.Series) -> float:
    var = market.var(ddof=1)
    if var == 0:
        return 0.0
    return float(r.cov(market) / var)


def correlation(a: pd.Series, b: pd.Series) -> float:
    c = a.corr(b)
    return 0.0 if pd.isna(c) else float(c)
