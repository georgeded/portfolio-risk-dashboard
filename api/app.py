import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from risk import config
from risk import data, report

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

app = FastAPI(
    title="Portfolio Risk Dashboard API",
    version="0.2.0",
    description="Risk metrics, risk contribution, correlation, warnings and stress tests for a list of tickers.",
)


@app.exception_handler(Exception)
def unexpected_error(request, exc):
    return JSONResponse(status_code=500, content={"detail": "The server hit an unexpected error. Please run it again."})


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
    currency: str | None = Field(None, description="Quote currency, for example EUR or GBp for pence. Looked up from Yahoo when left out.")


class ReportRequest(BaseModel):
    positions: list[Position]
    benchmark: str = config.DEFAULT_BENCHMARK
    lookback_days: int = Field(config.DEFAULT_LOOKBACK_DAYS, ge=config.MIN_LOOKBACK_DAYS, le=config.MAX_LOOKBACK_DAYS)
    confidence: float = Field(config.DEFAULT_CONFIDENCE, gt=0.5, lt=1.0)
    portfolio_value: float | None = Field(None, gt=0)
    base_currency: str = Field(config.DEFAULT_BASE_CURRENCY, description="Currency the risk is measured in. Positions in other currencies are converted.")
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


@app.get("/api/search")
def search(q: str = Query(..., min_length=1, max_length=40, description="Company name or ticker")):
    return {"results": data.search(q)}


@app.get("/api/lookup/{ticker}")
def lookup(ticker: str, base: str = config.DEFAULT_BASE_CURRENCY):
    try:
        ticker = data.normalize_ticker(ticker)
        base = report.currency_code(base, "base")
    except (data.DataError, report.InputError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        quoted = float(data.last_prices([ticker]).iloc[0])
    except data.DataError as e:
        raise HTTPException(status_code=404, detail=str(e))
    info = data.ticker_info(ticker)
    currency, scale = data.currency_unit(info["currency"])
    price = quoted * scale
    try:
        rate = 1.0 if currency == base else float(data.last_prices([data.fx_ticker(currency, base)]).iloc[0])
    except data.DataError:
        rate = None
    return {
        "ticker": ticker,
        "name": info["name"],
        "sector": info["sector"],
        "currency": currency,
        "last_price": price,
        "price_in_base": price * rate if rate is not None else None,
        "base_currency": base,
    }


@app.post("/api/report")
def report_post(req: ReportRequest):
    return _run(req)


@app.get("/api/report")
def report_get(
    tickers: str = Query(..., description="Comma separated, for example AAPL,MSFT,NVDA"),
    weights: str | None = Query(None, description="Comma separated, same order as tickers"),
    benchmark: str = config.DEFAULT_BENCHMARK,
    lookback_days: int = config.DEFAULT_LOOKBACK_DAYS,
    confidence: float = config.DEFAULT_CONFIDENCE,
    portfolio_value: float | None = None,
    base_currency: str = config.DEFAULT_BASE_CURRENCY,
):
    symbols = [t.strip() for t in tickers.split(",") if t.strip()]
    try:
        ws = [float(w) for w in weights.split(",")] if weights else [None] * len(symbols)
    except ValueError:
        raise HTTPException(status_code=400, detail="weights must be comma separated numbers")
    if len(ws) != len(symbols):
        raise HTTPException(status_code=400, detail="weights and tickers differ in length")
    req = ReportRequest(
        positions=[Position(ticker=t, weight=w) for t, w in zip(symbols, ws)],
        benchmark=benchmark,
        lookback_days=lookback_days,
        confidence=confidence,
        portfolio_value=portfolio_value,
        base_currency=base_currency,
    )
    return _run(req)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
