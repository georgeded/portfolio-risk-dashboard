import json
import os

import pandas as pd
import pytest

from risk import config, data


@pytest.mark.parametrize("ticker", ["AAPL", "brk-b", "ASML.AS", "^GSPC", "EURUSD=X", "7203.T"])
def test_valid_tickers(ticker):
    assert data.normalize_ticker(ticker) == ticker.upper()


@pytest.mark.parametrize("ticker", ["", "../secret", "a/b", "..", ".hidden", "AAPL MSFT", "x" * 21])
def test_invalid_tickers_rejected(ticker):
    with pytest.raises(data.DataError):
        data.normalize_ticker(ticker)


def test_cache_path_stays_in_cache_dir():
    with pytest.raises(data.DataError):
        data._cache_path("../secret.csv")
    assert os.path.dirname(data._cache_path("AAPL.csv")) == os.path.realpath(config.CACHE_DIR)


def test_stale_ticker_is_reported_instead_of_cutting_the_window():
    prices = pd.read_csv(config.PRICES_CSV, index_col=0, parse_dates=True)
    stale = prices.copy()
    stale.loc[stale.index[-40]:, "DDD"] = None
    with pytest.raises(data.DataError, match="DDD"):
        data._check_stale(stale)
    data._check_stale(prices)


def test_minor_currency_units():
    assert data.currency_unit("GBp") == ("GBP", 0.01)
    assert data.currency_unit("GBP") == ("GBP", 1.0)
    assert data.currency_unit(None) == ("USD", 1.0)


def test_incomplete_yahoo_info_is_fetched_again(monkeypatch, tmp_path):
    answers = [
        {"shortName": "Apple Inc.", "quoteType": "EQUITY"},
        {"shortName": "ASML Holding N.V. - New York Re", "longName": "Apple Inc.", "sector": "Technology", "quoteType": "EQUITY"},
    ]
    calls = []

    class FakeTicker:
        def __init__(self, ticker):
            calls.append(ticker)
            self.info = answers[len(calls) - 1]

    monkeypatch.setitem(__import__("sys").modules, "yfinance", type("yf", (), {"Ticker": FakeTicker}))
    monkeypatch.setattr(config, "PRICES_CSV", None)
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path))

    assert data.ticker_info("AAPL")["sector"] is None
    assert data.ticker_info("AAPL")["sector"] is None and len(calls) == 1

    store = json.loads((tmp_path / "info.json").read_text())
    store["AAPL"]["fetched"] -= 2 * 3600
    (tmp_path / "info.json").write_text(json.dumps(store))
    info = data.ticker_info("AAPL")
    assert info == {"name": "Apple Inc.", "sector": "Technology", "currency": None}
    assert len(calls) == 2
    data.ticker_info("AAPL")
    assert len(calls) == 2


def test_funds_without_a_sector_are_cached(monkeypatch, tmp_path):
    calls = []

    class FakeTicker:
        def __init__(self, ticker):
            calls.append(ticker)
            self.info = {"longName": "SPDR S&P 500 ETF Trust", "quoteType": "ETF"}

    monkeypatch.setitem(__import__("sys").modules, "yfinance", type("yf", (), {"Ticker": FakeTicker}))
    monkeypatch.setattr(config, "PRICES_CSV", None)
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path))
    store = {"SPY": {"name": "SPY", "sector": None, "currency": None, "complete": True, "fetched": 0}}
    (tmp_path / "info.json").write_text(json.dumps(store))
    assert data.ticker_info("SPY")["name"] == "SPY" and not calls
    store.pop("SPY")
    (tmp_path / "info.json").write_text(json.dumps(store))
    data.ticker_info("SPY")
    data.ticker_info("SPY")
    assert len(calls) == 1
