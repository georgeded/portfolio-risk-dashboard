import json
import os
import re
import threading
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

    with _download_lock:
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


def _read_cached(path: str) -> pd.Series | None:
    if not _fresh(path):
        return None
    try:
        return pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
    except (OSError, ValueError, IndexError):
        return None


def _yahoo_prices(tickers: list[str]) -> pd.DataFrame:
    frames = []
    missing = []
    for t in tickers:
        s = _read_cached(_cache_path(f"{t}.csv"))
        if s is None:
            missing.append(t)
        else:
            frames.append(s.rename(t))

    if missing:
        close = _download(missing)
        for t in missing:
            if t not in close.columns or close[t].dropna().empty:
                raise DataError(f"No price history for {t}")
            s = close[t].dropna()
            path = _cache_path(f"{t}.csv")
            tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
            s.to_csv(tmp, header=[t])
            os.replace(tmp, path)
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


# Funds and indices have no sector, so a lookup without one is still complete.
NO_SECTOR_TYPES = {"ETF", "INDEX", "MUTUALFUND", "CURRENCY", "CRYPTOCURRENCY"}
RETRY_INCOMPLETE_HOURS = 1
_info_lock = threading.Lock()
# yfinance keeps download results in module globals, so overlapping downloads can mix them up.
_download_lock = threading.Lock()


def _read_store(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_store(path: str, store: dict) -> None:
    # Write to a temporary file and swap it in, so readers never see half a file.
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w") as f:
        json.dump(store, f, indent=1)
    os.replace(tmp, path)


def ticker_info(ticker: str) -> dict:
    """Name, sector and quote currency from Yahoo, cached on disk. Empty fields when offline."""
    ticker = normalize_ticker(ticker)
    path = _cache_path("info.json")
    with _info_lock:
        cached = _read_store(path).get(ticker)
    # Yahoo sometimes answers without a sector; such entries are fetched again later.
    if cached and (cached.get("complete", True) or time.time() - cached.get("fetched", 0) < RETRY_INCOMPLETE_HOURS * 3600):
        return {k: cached[k] for k in ("name", "sector", "currency")}

    entry = {"name": ticker, "sector": None, "currency": None}
    if config.PRICES_CSV:
        return entry
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    if not info.get("longName") and not info.get("shortName"):
        return {k: cached[k] for k in ("name", "sector", "currency")} if cached else entry
    entry = {
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "currency": info.get("currency"),
    }
    with _info_lock:
        store = _read_store(path)
        store[ticker] = {**entry, "complete": bool(entry["sector"]) or info.get("quoteType") in NO_SECTOR_TYPES,
                         "fetched": time.time()}
        _write_store(path, store)
    return entry


SEARCH_TYPES = {"EQUITY", "ETF", "INDEX", "MUTUALFUND"}
_search_cache: dict[str, list[dict]] = {}


def search(query: str, limit: int = 8) -> list[dict]:
    """Tickers matching a name or symbol, for suggestions while typing."""
    q = query.strip()
    if not q:
        return []
    if config.PRICES_CSV:
        columns = pd.read_csv(config.PRICES_CSV, nrows=0).columns[1:]
        return [{"ticker": c.upper(), "name": c.upper(), "exchange": None, "type": None}
                for c in columns if c.upper().startswith(q.upper())][:limit]

    key = q.lower()
    if key not in _search_cache:
        try:
            import yfinance as yf

            quotes = yf.Search(q, max_results=limit * 2, news_count=0).quotes
        except Exception:
            return []
        results = []
        for item in quotes:
            symbol = str(item.get("symbol") or "").upper()
            if item.get("quoteType") not in SEARCH_TYPES or not TICKER_PATTERN.match(symbol):
                continue
            results.append({
                "ticker": symbol,
                "name": item.get("longname") or item.get("shortname") or symbol,
                "exchange": item.get("exchDisp"),
                "type": item.get("quoteType").lower(),
            })
        if len(_search_cache) > 500:
            _search_cache.clear()
        _search_cache[key] = results
    return _search_cache[key][:limit]


def simple_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().iloc[1:].replace([np.inf, -np.inf], np.nan).fillna(0.0)
