import os

TRADING_DAYS = 252

DEFAULT_BENCHMARK = "SPY"
DEFAULT_LOOKBACK_DAYS = 252
MIN_LOOKBACK_DAYS = 60
MAX_LOOKBACK_DAYS = 1250
DEFAULT_CONFIDENCE = 0.95
DEFAULT_RISK_FREE_RATE = 0.0
DEFAULT_BASE_CURRENCY = "USD"

# Set PRICES_CSV to a file with a Date column and one column per ticker to run
# without network access. Otherwise prices come from Yahoo Finance.
PRICES_CSV = os.environ.get("PRICES_CSV")
CACHE_DIR = os.environ.get("CACHE_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache"))
CACHE_TTL_HOURS = float(os.environ.get("CACHE_TTL_HOURS", "12"))
DOWNLOAD_YEARS = 6

# Gaps of up to this many trading days are filled forward. A ticker with no
# price for longer than that is reported as stale instead of cutting the window.
MAX_GAP_DAYS = 5

ALLOWED_ORIGINS = [o for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o]

# Macro factors used by the stress tests. Each position gets a beta to every
# factor from one joint regression on daily returns.
FACTORS = {
    "market": "SPY",
    "rates": "TLT",
    "dollar": "UUP",
}

# Yahoo sector name to the SPDR sector ETF used as the factor for a sector crash.
SECTOR_ETFS = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}
