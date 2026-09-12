import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from risk import data, report

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

app = FastAPI(
    title="Portfolio Risk Dashboard API",
    version="0.1.0",
    description="Risk metrics, risk contribution, correlation, warnings and stress tests for a list of tickers.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class Position(BaseModel):
    ticker: str = Field(..., examples=["AAPL"])
    weight: float | None = Field(None, description="Share of the book. Any scale, weights are normalized.")
    quantity: float | None = Field(None, description="Number of shares. Value uses the latest price.")
    name: str | None = None
    sector: str | None = Field(None, description="Overrides the sector looked up from Yahoo.")
    currency: str | None = Field(None, description="Quote currency of the position, default USD.")


class ReportRequest(BaseModel):
    positions: list[Position]
    benchmark: str = config.DEFAULT_BENCHMARK
    lookback_days: int = Field(config.DEFAULT_LOOKBACK_DAYS, ge=config.MIN_LOOKBACK_DAYS, le=config.MAX_LOOKBACK_DAYS)
    confidence: float = Field(config.DEFAULT_CONFIDENCE, gt=0.5, lt=1.0)
    portfolio_value: float | None = Field(None, gt=0)
    base_currency: str = config.DEFAULT_BASE_CURRENCY
    risk_free_rate: float = config.DEFAULT_RISK_FREE_RATE

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "positions": [
                    {"ticker": "AAPL", "weight": 0.25},
                    {"ticker": "MSFT", "weight": 0.20},
                    {"ticker": "NVDA", "weight": 0.20},
                    {"ticker": "JPM", "weight": 0.15},
                    {"ticker": "XOM", "weight": 0.10},
                    {"ticker": "ASML", "weight": 0.10},
                ],
                "benchmark": "SPY",
                "lookback_days": 252,
                "confidence": 0.95,
                "portfolio_value": 100000,
                "base_currency": "USD",
            }]
        }
    }


def _run(req: ReportRequest) -> dict:
    try:
        return report.build_report(
            positions=[p.model_dump() for p in req.positions],
            benchmark=req.benchmark,
            lookback_days=req.lookback_days,
            confidence=req.confidence,
            portfolio_value=req.portfolio_value,
            base_currency=req.base_currency,
            risk_free_rate=req.risk_free_rate,
        )
    except (report.InputError, data.DataError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/health")
def health():
    return {"status": "ok", "price_source": "csv" if config.PRICES_CSV else "yahoo"}


@app.get("/api/scenarios")
def scenarios():
    return {"factors": config.FACTORS, "sector_etfs": config.SECTOR_ETFS, "scenarios": config.SCENARIOS}


@app.get("/api/thresholds")
def thresholds():
    return {"thresholds": config.THRESHOLDS, "risk_meter": config.RISK_METER,
            "levels": [{"below": cap, "level": name} for cap, name in config.RISK_LEVELS]}


@app.post("/api/report")
def report_post(req: ReportRequest):
    return _run(req)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
