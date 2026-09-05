import math

import numpy as np
import pandas as pd

from risk import metrics


def test_norm_ppf_matches_known_values():
    assert abs(metrics.norm_ppf(0.975) - 1.959964) < 1e-5
    assert abs(metrics.norm_ppf(0.05) + 1.644854) < 1e-5
    assert abs(metrics.norm_ppf(0.5)) < 1e-9


def test_max_drawdown_finds_peak_and_trough():
    r = pd.Series([0.10, -0.05, -0.20, 0.10, 0.30],
                  index=pd.bdate_range("2024-01-01", periods=5))
    dd = metrics.max_drawdown(r)
    assert abs(dd["max_drawdown"] - (0.95 * 0.8 - 1)) < 1e-12
    assert dd["peak_date"] == "2024-01-01"
    assert dd["trough_date"] == "2024-01-03"
    assert dd["recovery_date"] == "2024-01-05"
    assert dd["current_drawdown"] == 0.0


def test_var_and_cvar_are_ordered():
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0, 0.01, 2000))
    var95 = metrics.var_historical(r, 0.95)
    cvar95 = metrics.cvar_historical(r, 0.95)
    var99 = metrics.var_historical(r, 0.99)
    assert cvar95 < var95 < 0
    assert var99 < var95
    assert abs(metrics.var_parametric(r, 0.95) - var95) < 0.003


def test_risk_contributions_sum_to_volatility():
    cov = np.array([[0.04, 0.01, 0.0], [0.01, 0.09, 0.02], [0.0, 0.02, 0.16]])
    w = np.array([0.5, 0.3, 0.2])
    rc = metrics.risk_contributions(w, cov)
    assert abs(rc["contribution"].sum() - rc["volatility"]) < 1e-12
    assert abs(rc["share"].sum() - 1) < 1e-12
    assert abs(rc["volatility"] - math.sqrt(w @ cov @ w)) < 1e-12


def test_concentration_of_equal_weights():
    c = metrics.concentration(np.full(8, 0.125))
    assert abs(c["hhi"] - 0.125) < 1e-12
    assert abs(c["effective_positions"] - 8) < 1e-9
    assert abs(c["top3_weight"] - 0.375) < 1e-12


def test_stress_correlation_only_raises():
    corr = np.array([[1.0, 0.2, -0.5], [0.2, 1.0, 0.9], [-0.5, 0.9, 1.0]])
    stressed = metrics.stress_correlation(corr, 0.8)
    assert stressed[0, 1] == 0.8
    assert stressed[1, 2] == 0.9
    assert stressed[0, 2] == 0.8
    assert np.allclose(np.diag(stressed), 1.0)


def test_annualized_return_of_constant_growth():
    r = pd.Series([0.001] * 252)
    assert abs(metrics.annualized_return(r) - (1.001 ** 252 - 1)) < 1e-12
    assert metrics.annualized_volatility(r) < 1e-12
    assert metrics.sharpe_ratio(pd.Series([0.0] * 252)) is None
