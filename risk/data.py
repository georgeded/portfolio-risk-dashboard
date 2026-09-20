import json
import os
import time

import numpy as np
import pandas as pd

import config


class DataError(Exception):
    pass


def _cache_path(name: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, name)


def _fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    return age_hours < config.CACHE_TTL_HOURS


def _download(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(
        tickers,
        period=f"{config.DOWNLOAD_YEARS}y",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw is None or raw.empty:
        return pd.DataFrame()
    close = raw["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


def _yahoo_prices(tickers: list[str]) -> pd.DataFrame:
    frames = []
    missing = []
    for t in tickers:
        path = _cache_path(f"{t}.csv")
        if _fresh(path):
            s = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
            frames.append(s.rename(t))
        else:
            missing.append(t)

    if missing:
        close = _download(missing)
        for t in missing:
            if t not in close.columns or close[t].dropna().empty:
                raise DataError(f"No price history for {t}")
            s = close[t].dropna()
            s.to_csv(_cache_path(f"{t}.csv"), header=[t])
            frames.append(s.rename(t))

    return pd.concat(frames, axis=1).sort_index()


def _csv_prices(tickers: list[str]) -> pd.DataFrame:
    df = pd.read_csv(config.PRICES_CSV, index_col=0, parse_dates=True).sort_index()
    df.columns = [c.upper() for c in df.columns]
    absent = [t for t in tickers if t not in df.columns]
    if absent:
        raise DataError(f"Not in {config.PRICES_CSV}: {', '.join(absent)}")
    return df[tickers]


def load_prices(tickers: list[str], lookback_days: int) -> pd.DataFrame:
    """Adjusted close for the last `lookback_days` trading days, one column per ticker.

    Gaps of up to five days are filled forward so tickers on different
    exchange calendars line up. Rows where any ticker is still missing are dropped.
    """
    tickers = list(dict.fromkeys(t.upper() for t in tickers))
    prices = _csv_prices(tickers) if config.PRICES_CSV else _yahoo_prices(tickers)
    prices = prices.ffill(limit=5).dropna()
    if len(prices) < config.MIN_LOOKBACK_DAYS:
        raise DataError(
            f"Only {len(prices)} overlapping trading days, need {config.MIN_LOOKBACK_DAYS}"
        )
    return prices.iloc[-(lookback_days + 1):]


def last_prices(tickers: list[str]) -> pd.Series:
    prices = load_prices(tickers, config.MIN_LOOKBACK_DAYS)
    return prices.iloc[-1]


def ticker_info(ticker: str) -> dict:
    """Name, sector and currency from Yahoo, cached on disk. Empty fields when offline."""
    ticker = ticker.upper()
    path = _cache_path("info.json")
    store = {}
    if os.path.exists(path):
        with open(path) as f:
            store = json.load(f)
    if ticker in store:
        return store[ticker]

    entry = {"name": ticker, "sector": None, "currency": None}
    if config.PRICES_CSV:
        return entry
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    if not info.get("shortName") and not info.get("sector"):
        return entry
    entry = {
        "name": info.get("shortName") or info.get("longName") or ticker,
        "sector": info.get("sector"),
        "currency": info.get("currency"),
    }
    store[ticker] = entry
    with open(path, "w") as f:
        json.dump(store, f, indent=1)
    return entry


def simple_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().iloc[1:].replace([np.inf, -np.inf], np.nan).fillna(0.0)
