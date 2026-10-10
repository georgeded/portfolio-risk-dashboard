import numpy as np
import pandas as pd
import pytest

from risk import config, data, report


def positions():
    return [
        {"ticker": "AAA", "weight": 40, "sector": "Technology"},
        {"ticker": "BBB", "weight": 30, "sector": "Financial Services"},
        {"ticker": "CCC", "weight": 20, "sector": "Energy"},
        {"ticker": "DDD", "weight": 10, "sector": "Technology"},
    ]


def test_weights_are_normalized():
    tickers, weights, value = report.resolve_positions(positions(), None)
    assert tickers == ["AAA", "BBB", "CCC", "DDD"]
    assert np.allclose(weights, [0.4, 0.3, 0.2, 0.1])
    assert value is None


def test_equal_weights_when_none_given():
    _, weights, _ = report.resolve_positions([{"ticker": "AAA"}, {"ticker": "BBB"}], None)
    assert np.allclose(weights, [0.5, 0.5])


def test_quantities_become_weights_and_value():
    prices = pd.Series({"AAA": 100.0, "BBB": 50.0})
    _, weights, value = report.resolve_positions(
        [{"ticker": "AAA", "quantity": 10}, {"ticker": "BBB", "quantity": 10}], None, prices)
    assert np.allclose(weights, [2 / 3, 1 / 3])
    assert value == 1500


def test_non_finite_weights_rejected():
    for bad in (float("nan"), float("inf")):
        with pytest.raises(report.InputError):
            report.resolve_positions([{"ticker": "AAA", "weight": bad}, {"ticker": "BBB", "weight": 1}], None)


def test_mixed_input_rejected():
    with pytest.raises(report.InputError):
        report.resolve_positions([{"ticker": "AAA", "weight": 1}, {"ticker": "BBB", "quantity": 1}], None)
    with pytest.raises(report.InputError):
        report.resolve_positions([{"ticker": "AAA"}, {"ticker": "aaa"}], None)


def test_full_report_shape():
    rep = report.build_report(positions(), lookback_days=252, portfolio_value=50000)
    for key in ("summary", "risk_meter", "warnings", "downside", "concentration",
                "correlation", "risk_contribution", "positions", "stress_tests", "series"):
        assert key in rep
    assert rep["window"]["trading_days"] == 252
    assert rep["window"]["sector_factor"] == "XLK"
    assert len(rep["series"]["dates"]) == 252
    assert rep["risk_meter"]["level"] in ("Low", "Moderate", "High", "Very High")

    shares = [p["share"] for p in rep["risk_contribution"]["positions"]]
    assert abs(sum(shares) - 1) < 1e-5

    matrix = np.array(rep["correlation"]["matrix"])
    assert matrix.shape == (4, 4)
    assert np.allclose(np.diag(matrix), 1.0)

    codes = {w["code"] for w in rep["warnings"]}
    assert "position_weight" in codes
    assert "top3_weight" in codes
    assert "sector_weight" in codes

    assert rep["downside"]["cvar_historical"] <= rep["downside"]["var_historical"]
    assert abs(rep["downside"]["var_historical_value"] - rep["downside"]["var_historical"] * 50000) < 0.05


def test_stress_tests():
    rep = report.build_report(positions(), portfolio_value=10000)
    tests = {t["id"]: t for t in rep["stress_tests"]}
    assert set(tests) == {"market_crash", "rate_shock", "recession", "sector_crash",
                          "fx_move", "correlation_spike"}
    crash = tests["market_crash"]
    assert crash["portfolio_loss_pct"] < -0.10
    assert abs(sum(p["loss_pct"] for p in crash["positions"]) - crash["portfolio_loss_pct"]) < 1e-5
    losers = [p for p in crash["positions"] if p["loss_pct"] < 0]
    assert abs(sum(p["share_of_loss"] for p in losers) - 1) < 1e-5
    assert abs(crash["portfolio_loss_value"] - crash["portfolio_loss_pct"] * 10000) < 0.05

    spike = tests["correlation_spike"]
    assert spike["details"]["volatility_after"] >= spike["details"]["volatility_before"]
    assert spike["portfolio_loss_pct"] < 0
    assert tests["sector_crash"]["sector"] == "Technology"


def test_fx_translation_for_euro_book():
    usd = report.build_report(positions(), base_currency="USD")
    eur = report.build_report(positions(), base_currency="EUR")
    fx_usd = next(t for t in usd["stress_tests"] if t["id"] == "fx_move")
    fx_eur = next(t for t in eur["stress_tests"] if t["id"] == "fx_move")
    assert abs((fx_eur["portfolio_loss_pct"] - fx_usd["portfolio_loss_pct"]) + 0.10) < 1e-5


def test_mixed_currency_book_is_measured_in_the_base_currency():
    rep = report.build_report([{"ticker": "AAA", "weight": 1, "currency": "EUR"}], base_currency="USD")
    prices = pd.read_csv(config.PRICES_CSV, index_col=0, parse_dates=True)
    window = prices.loc[rep["window"]["start"]:rep["window"]["end"]]
    start = prices.index[prices.index.get_loc(window.index[0]) - 1]
    in_usd = prices["AAA"] * prices["EURUSD=X"]
    expected = in_usd[window.index[-1]] / in_usd[start] - 1
    assert abs(rep["summary"]["period_return"] - expected) < 1e-5
    assert rep["portfolio"]["currencies"] == ["EUR"]


def test_quantities_in_other_currencies_are_converted():
    eur = report.build_report([{"ticker": "AAA", "quantity": 10, "currency": "EUR"}], base_currency="USD")
    usd = report.build_report([{"ticker": "AAA", "quantity": 10, "currency": "USD"}], base_currency="USD")
    prices = pd.read_csv(config.PRICES_CSV, index_col=0, parse_dates=True)
    rate = prices["EURUSD=X"].iloc[-1]
    assert abs(eur["portfolio"]["value"] / usd["portfolio"]["value"] - rate) < 1e-4


def test_pence_prices_are_scaled_to_pounds():
    rep = report.build_report([{"ticker": "AAA", "weight": 1, "currency": "GBp"}], base_currency="USD")
    prices = pd.read_csv(config.PRICES_CSV, index_col=0, parse_dates=True)
    assert abs(rep["positions"][0]["last_price"] - prices["AAA"].iloc[-1] / 100) < 1e-4
    assert rep["positions"][0]["currency"] == "GBP"


def test_stale_ticker_names_the_problem(monkeypatch):
    prices = pd.read_csv(config.PRICES_CSV, index_col=0, parse_dates=True)
    prices.loc[prices.index[-40]:, "DDD"] = None
    monkeypatch.setattr(data, "_csv_prices", lambda tickers: prices[tickers])
    with pytest.raises(data.DataError, match="No recent prices for DDD"):
        report.build_report(positions())


def test_drawdown_from_day_one_drives_meter_and_warning(monkeypatch):
    prices = pd.read_csv(config.PRICES_CSV, index_col=0, parse_dates=True)
    crash = prices.copy()
    start = crash.index[-61]
    crash.loc[crash.index > start, "AAA"] = crash.loc[start, "AAA"] * 0.6
    monkeypatch.setattr(data, "_csv_prices", lambda tickers: crash[tickers])
    rep = report.build_report([{"ticker": "AAA", "weight": 1}], lookback_days=60)
    assert rep["summary"]["max_drawdown"] < -0.39
    assert rep["summary"]["drawdown_peak_date"] == start.strftime("%Y-%m-%d")
    assert "max_drawdown" in {w["code"] for w in rep["warnings"]}
    component = next(c for c in rep["risk_meter"]["components"] if c["key"] == "max_drawdown")
    assert component["score"] == 100.0
