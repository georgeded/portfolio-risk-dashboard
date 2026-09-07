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
