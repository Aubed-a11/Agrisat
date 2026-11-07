import numpy as np
import pytest

from agrisat_core import phenology as ph
from agrisat_core.communes import CROP_PARAMS
from agrisat_core.features import contract_index
from agrisat_core.actuarial.contract import payout_fraction
from agrisat_core.actuarial.pricing import premium_from_payouts, var_cvar, wang_premium
from agrisat_core.actuarial.basis_risk import basis_risk_metrics
from agrisat_core.actuarial.optimize import crra_ce
from agrisat_core.actuarial.weather_generator import RainGenerator


def test_payout_linear_between_trigger_and_exit():
    T, E, w = [100, 100, 100, 100], [50, 50, 50, 50], [0.25] * 4
    assert payout_fraction([[120] * 4], T, E, w)[0] == 0.0
    assert payout_fraction([[40] * 4], T, E, w)[0] == pytest.approx(1.0)
    assert payout_fraction([[75] * 4], T, E, w)[0] == pytest.approx(0.5)
    assert payout_fraction([[75, 120, 120, 120]], T, E, w)[0] == pytest.approx(0.125)


def test_payout_capped_at_one():
    assert payout_fraction([[0] * 4], [10] * 4, [5] * 4, [0.5] * 4)[0] == 1.0


def test_onset_detection():
    rain = np.zeros((2, 365), np.float32)
    rain[0, 150:153] = 7.0
    rain[0, 155:200:3] = 5.0
    rain[1, 120:123] = 10.0   # faux depart: rien ensuite
    on = ph.detect_onset(rain)
    assert on[0] == 150
    assert on[1] == ph.ONSET_SEARCH_END


def test_contract_index_shape_and_cap():
    rain = np.full((3, 365), 100.0, np.float32)
    idx = contract_index(rain, CROP_PARAMS["coton"])
    assert idx.shape == (3, 4)
    assert idx[0, 0] == pytest.approx(50.0 * CROP_PARAMS["coton"]["phase_lengths"][0])


def test_premium_components():
    frac = np.r_[np.zeros(900), np.ones(100) * 0.5]
    pr = premium_from_payouts(frac, 100000, subsidy_rate=0.8, expense_rate=0.25, cost_of_capital=0.1)
    assert pr["pure_premium"] == pytest.approx(5000.0)
    assert pr["commercial_premium"] > pr["pure_premium"]
    assert pr["farmer_premium"] + pr["subsidy"] == pytest.approx(pr["commercial_premium"], abs=0.2)
    assert pr["prob_payout"] == pytest.approx(0.1)


def test_var_cvar_and_wang():
    x = np.arange(1000, dtype=float)
    v, c = var_cvar(x, 0.99)
    assert v <= c
    assert wang_premium(x, 0.25) > x.mean()
    assert wang_premium(x, 0.0) == pytest.approx(x.mean(), rel=1e-3)


def test_basis_risk_metrics():
    pay = np.array([0, 0, 0.5, 1.0, 0.2])
    loss = np.array([0.0, 0.4, 0.5, 0.6, 0.05])
    m = basis_risk_metrics(pay, loss)
    assert m["false_negative_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert m["false_positive_rate"] == pytest.approx(1 / 3, abs=1e-3)


def test_crra_ce_risk_aversion():
    x = np.array([50.0, 150.0])
    assert crra_ce(x, 2.0) < x.mean()
    assert crra_ce(np.array([100.0, 100.0]), 2.0) == pytest.approx(100.0)


def test_weather_generator_reproduces_climate():
    rng = np.random.default_rng(0)
    C, Y = 2, 30
    rain = np.zeros((C, Y, 365))
    wet = rng.random((C, Y, 365)) < 0.4
    rain[wet] = rng.gamma(0.8, 12, wet.sum()) + 1
    rain[:, :, :100] = 0
    g = RainGenerator().fit(rain)
    sims = next(g.simulate(500, seed=1, batch=500))
    assert sims.shape == (500, C, 365)
    assert sims.sum(axis=2).mean() == pytest.approx(rain.sum(axis=2).mean(), rel=0.12)
