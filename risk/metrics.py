import math

import numpy as np
import pandas as pd

from risk.config import TRADING_DAYS


def norm_ppf(p: float) -> float:
    """Inverse of the standard normal CDF (Acklam's rational approximation)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00)
    plow = 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - plow:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


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
    # The book is worth 1 before the first return, so a fall on day one counts.
    peak = wealth.cummax().clip(lower=1.0)
    return wealth / peak - 1


def max_drawdown(r: pd.Series, start=None) -> dict:
    """Largest peak to trough fall, with the dates around it and where we are now.

    `start` is the date the book is valued at 1, the close before the first
    return. It is reported as the peak when the fall begins on day one.
    """
    dd = drawdown_series(r)
    if dd.empty:
        return {"max_drawdown": 0.0, "current_drawdown": 0.0, "peak_date": None,
                "trough_date": None, "recovery_date": None}
    trough = dd.idxmin()
    wealth = (1 + r).cumprod()
    before = wealth.loc[:trough]
    if before.max() > 1.0:
        peak_date, peak_value = before.idxmax(), before.max()
    else:
        peak_date, peak_value = start, 1.0
    after = wealth.loc[trough:]
    recovered = after[after >= peak_value]
    recovery = recovered.index[0] if len(recovered) and recovered.index[0] != trough else None
    return {
        "max_drawdown": float(dd.min()),
        "current_drawdown": float(dd.iloc[-1]),
        "peak_date": _date(peak_date),
        "trough_date": _date(trough),
        "recovery_date": _date(recovery),
    }


def _date(d) -> str | None:
    return pd.Timestamp(d).strftime("%Y-%m-%d") if d is not None else None
