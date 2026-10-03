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
