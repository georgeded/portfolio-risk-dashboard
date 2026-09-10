import os
import tempfile

import numpy as np
import pandas as pd

# Point the app at a synthetic price file before config is imported so the
# tests never touch the network.
_tmp = tempfile.mkdtemp()
_csv = os.path.join(_tmp, "prices.csv")
os.environ["PRICES_CSV"] = _csv
os.environ["CACHE_DIR"] = os.path.join(_tmp, "cache")

TICKERS = ["AAA", "BBB", "CCC", "DDD", "SPY", "TLT", "UUP", "XLK"]


def _make_prices():
    rng = np.random.default_rng(7)
    n = 600
    market = rng.normal(0.0004, 0.010, n)
    rates = rng.normal(0.0, 0.006, n)
    dollar = rng.normal(0.0, 0.004, n)
    loads = {
        "AAA": (1.2, 0.0, 0.0, 0.012),
        "BBB": (0.9, -0.3, 0.0, 0.010),
        "CCC": (0.5, 0.4, 0.2, 0.015),
        "DDD": (1.5, 0.0, -0.3, 0.020),
        "SPY": (1.0, 0.0, 0.0, 0.0),
        "TLT": (0.0, 1.0, 0.0, 0.0),
        "UUP": (0.0, 0.0, 1.0, 0.0),
        "XLK": (1.1, 0.0, 0.0, 0.004),
    }
    dates = pd.bdate_range("2023-01-02", periods=n)
    out = {}
    for t, (bm, br, bd, noise) in loads.items():
        r = bm * market + br * rates + bd * dollar + rng.normal(0, noise, n)
        out[t] = 100 * np.cumprod(1 + r)
    pd.DataFrame(out, index=dates).rename_axis("Date").to_csv(_csv)


_make_prices()
