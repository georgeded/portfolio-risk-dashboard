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
