import numpy as np
import pytest

from risk import report


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
    _, weights, value = report.resolve_positions(
        [{"ticker": "AAA", "quantity": 10}, {"ticker": "BBB", "quantity": 10}], None)
    assert abs(weights.sum() - 1) < 1e-12
    assert value > 0


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
