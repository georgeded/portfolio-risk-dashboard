import json
import os
import re
import time

import numpy as np
import pandas as pd

from risk import config


class DataError(Exception):
    pass


# Yahoo symbols: AAPL, BRK-B, ASML.AS, ^GSPC, EURUSD=X.
TICKER_PATTERN = re.compile(r"^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$")

# Yahoo quotes some exchanges in minor units, for example London in pence.
MINOR_UNITS = {"GBP": ("GBP", 0.01), "GBX": ("GBP", 0.01), "ZAC": ("ZAR", 0.01), "ILA": ("ILS", 0.01)}


def normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip().upper()
    if not TICKER_PATTERN.match(t):
        raise DataError(f"Not a valid ticker: {ticker!r}")
    return t


def currency_unit(code: str | None) -> tuple[str, float]:
    """ISO currency and the factor that turns a quoted price into it."""
    if not code:
        return "USD", 1.0
    if code in ("GBp", "GBX", "ZAc", "ILA"):
        return MINOR_UNITS[code.upper()]
    return code.upper(), 1.0


def fx_ticker(currency: str, base: str) -> str:
    """Yahoo symbol for the price of one unit of `currency` in `base`."""
    return f"{currency}{base}=X"


def _cache_path(name: str) -> str:
    root = os.path.realpath(config.CACHE_DIR)
    os.makedirs(root, exist_ok=True)
    path = os.path.realpath(os.path.join(root, name))
    if os.path.dirname(path) != root:
        raise DataError(f"Invalid cache name: {name!r}")
    return path


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


def _check_stale(prices: pd.DataFrame) -> None:
    # Without this, dropping incomplete rows would quietly end the window on
    # the last day a delisted or halted ticker traded.
    stale = []
    for t in prices.columns:
        last = prices[t].last_valid_index()
        if last is None:
            raise DataError(f"No price history for {t}")
        if (prices.index > last).sum() > config.MAX_GAP_DAYS:
            stale.append(f"{t} (last price {last:%Y-%m-%d})")
    if stale:
        raise DataError(f"No recent prices for {', '.join(stale)}. Remove them or check the symbols.")


def load_prices(tickers: list[str], lookback_days: int) -> pd.DataFrame:
    """Adjusted close for the last `lookback_days` trading days, one column per ticker.

    Short gaps are filled forward so tickers on different exchange calendars
    line up. Rows where any ticker is still missing are dropped.
    """
    tickers = list(dict.fromkeys(normalize_ticker(t) for t in tickers))
    prices = _csv_prices(tickers) if config.PRICES_CSV else _yahoo_prices(tickers)
    _check_stale(prices)
    prices = prices.ffill(limit=config.MAX_GAP_DAYS).dropna()
    if len(prices) < config.MIN_LOOKBACK_DAYS:
        raise DataError(
            f"Only {len(prices)} overlapping trading days, need {config.MIN_LOOKBACK_DAYS}"
        )
    return prices.iloc[-(lookback_days + 1):]


def last_prices(tickers: list[str]) -> pd.Series:
    prices = load_prices(tickers, config.MIN_LOOKBACK_DAYS)
    return prices.iloc[-1]
