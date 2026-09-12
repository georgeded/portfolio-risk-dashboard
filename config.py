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

# Shocks are fractional moves of the factor over the scenario. A position moves
# by the sum of beta times shock across the shocked factors.
SCENARIOS = [
    {
        "id": "market_crash",
        "name": "Market crash",
        "description": "The equity market falls 20% with rates and the dollar unchanged.",
        "shocks": {"market": -0.20},
    },
    {
        "id": "rate_shock",
        "name": "Sharp interest rate move",
        "description": "Yields jump and long Treasuries fall 10%, roughly a 100bp move.",
        "shocks": {"rates": -0.10},
    },
    {
        "id": "recession",
        "name": "Recession",
        "description": "Equities fall 30%, long Treasuries rally 10% and the dollar gains 5%.",
        "shocks": {"market": -0.30, "rates": 0.10, "dollar": 0.05},
    },
    {
        "id": "sector_crash",
        "name": "Sector crash",
        "description": "The portfolio's largest sector falls 25%.",
        "shocks": {"sector": -0.25},
    },
    {
        "id": "fx_move",
        "name": "Large FX move",
        "description": "The dollar falls 10% against other currencies.",
        "shocks": {"dollar": -0.10},
        "translation": True,
    },
    {
        "id": "correlation_spike",
        "name": "Correlations rise",
        "description": "Every pairwise correlation rises to at least 0.8 and the portfolio has a bad ten days.",
        "correlation_floor": 0.8,
        "horizon_days": 10,
        "confidence": 0.99,
    },
]

# Warning thresholds. Losses and drawdowns are negative fractions.
THRESHOLDS = {
    "max_position_weight": 0.15,
    "top3_weight": 0.50,
    "max_sector_weight": 0.40,
    "min_effective_positions": 5,
    "annualized_volatility": 0.30,
    "max_drawdown": -0.20,
    "cvar_95_daily": -0.03,
    "average_correlation": 0.60,
    "beta": 1.30,
    "risk_share_vs_weight": 2.0,
}

# Risk meter: each component is scored 0 to 100 between a low and a high
# anchor, then blended with the weights below.
RISK_METER = {
    "volatility": {"low": 0.10, "high": 0.40, "weight": 0.30},
    "max_drawdown": {"low": 0.05, "high": 0.40, "weight": 0.20},
    "cvar": {"low": 0.01, "high": 0.05, "weight": 0.20},
    "concentration": {"low": 0.05, "high": 0.35, "weight": 0.15},
    "correlation": {"low": 0.20, "high": 0.80, "weight": 0.15},
}
RISK_LEVELS = [(25, "Low"), (50, "Moderate"), (75, "High"), (101, "Very High")]
