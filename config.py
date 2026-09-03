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
CACHE_DIR = os.environ.get("CACHE_DIR", os.path.join(os.path.dirname(__file__), "cache"))
CACHE_TTL_HOURS = float(os.environ.get("CACHE_TTL_HOURS", "12"))
DOWNLOAD_YEARS = 6
