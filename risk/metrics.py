import math

import numpy as np
import pandas as pd

from config import TRADING_DAYS


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


def var_historical(r: pd.Series, confidence: float) -> float:
    return float(np.quantile(r.values, 1 - confidence))


def cvar_historical(r: pd.Series, confidence: float) -> float:
    cut = var_historical(r, confidence)
    tail = r[r <= cut]
    return float(tail.mean()) if len(tail) else cut


def var_parametric(r: pd.Series, confidence: float) -> float:
    return float(r.mean() + r.std(ddof=1) * norm_ppf(1 - confidence))


def cvar_parametric(r: pd.Series, confidence: float) -> float:
    z = norm_ppf(1 - confidence)
    return float(r.mean() - r.std(ddof=1) * norm_pdf(z) / (1 - confidence))


def parametric_from_moments(mean: float, std: float, confidence: float, horizon_days: int = 1) -> dict:
    z = norm_ppf(1 - confidence)
    scale = math.sqrt(horizon_days)
    m = mean * horizon_days
    s = std * scale
    return {
        "var": m + s * z,
        "cvar": m - s * norm_pdf(z) / (1 - confidence),
    }


def worst_windows(r: pd.Series, windows=(1, 5, 20)) -> list[dict]:
    out = []
    for w in windows:
        if len(r) < w:
            continue
        rolled = (1 + r).rolling(w).apply(np.prod, raw=True) - 1
        rolled = rolled.dropna()
        end = rolled.idxmin()
        start = r.index[r.index.get_loc(end) - w + 1]
        out.append({
            "days": w,
            "return": float(rolled.min()),
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
        })
    return out


def risk_contributions(weights: np.ndarray, cov: np.ndarray) -> dict:
    """Euler decomposition of portfolio volatility.

    contribution_i = w_i * (cov w)_i / sigma and the contributions sum to sigma.
    """
    cov = np.asarray(cov, dtype=float)
    w = np.asarray(weights, dtype=float)
    variance = float(w @ cov @ w)
    sigma = math.sqrt(max(variance, 0.0))
    if sigma == 0:
        n = len(w)
        return {"volatility": 0.0, "marginal": np.zeros(n), "contribution": np.zeros(n),
                "share": np.full(n, 1 / n if n else 0.0)}
    marginal = cov @ w / sigma
    contribution = w * marginal
    return {
        "volatility": sigma,
        "marginal": marginal,
        "contribution": contribution,
        "share": contribution / sigma,
    }


def annualize_cov(cov_daily: np.ndarray) -> np.ndarray:
    return np.asarray(cov_daily) * TRADING_DAYS


def concentration(weights: np.ndarray) -> dict:
    w = np.abs(np.asarray(weights, dtype=float))
    total = w.sum()
    if total == 0:
        return {"hhi": 0.0, "effective_positions": 0.0, "top1_weight": 0.0, "top3_weight": 0.0}
    w = w / total
    hhi = float((w ** 2).sum())
    ordered = np.sort(w)[::-1]
    return {
        "hhi": hhi,
        "effective_positions": 1 / hhi if hhi > 0 else 0.0,
        "top1_weight": float(ordered[0]),
        "top3_weight": float(ordered[:3].sum()),
    }


def stress_correlation(corr: np.ndarray, floor: float) -> np.ndarray:
    stressed = np.maximum(np.asarray(corr, dtype=float), floor)
    np.fill_diagonal(stressed, 1.0)
    return stressed


def cov_from_corr(corr: np.ndarray, stds: np.ndarray) -> np.ndarray:
    d = np.diag(stds)
    return d @ corr @ d
