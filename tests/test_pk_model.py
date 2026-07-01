# test script for pk_model.py

import math
import numpy as np
import pytest
from brewmetheus.models import PKParams
from brewmetheus.pk_model import (
    auc,
    cmax,
    concentration_curve,
    concentration_single,
    tmax_h,
)


def _params(ka: float = 6.0, ke: float = 0.1386, v: float = 35.0, f: float = 1.0) -> PKParams:
    half_life = math.log(2) / ke if ke > 0 else 0.0
    return PKParams(F=f, V_l=v, ka_per_h=ka, ke_per_h=ke, effective_half_life_h=half_life)


def test_before_dose_is_zero() -> None:
    p = _params()
    assert concentration_single(-1.0, 100.0, p) == 0.0
    grid = np.linspace(-5.0, -0.001, 50)
    assert np.all(concentration_single(grid, 100.0, p) == 0.0)


def test_non_negative_over_day() -> None:
    p = _params()
    t = np.linspace(0.0, 48.0, 2881)
    c = concentration_single(t, 200.0, p)
    assert np.all(c >= 0.0)


def test_tmax_matches_analytic() -> None:
    p = _params()
    t = np.linspace(0.0, 12.0, 120_001)  # ~0.36 s resolution
    c = np.asarray(concentration_single(t, 200.0, p))
    numeric_tmax = float(t[int(np.argmax(c))])
    assert math.isclose(numeric_tmax, tmax_h(p), rel_tol=1e-3, abs_tol=1e-3)


def test_cmax_matches_peak() -> None:
    p = _params()
    t = np.linspace(0.0, 12.0, 120_001)
    c = np.asarray(concentration_single(t, 200.0, p))
    assert math.isclose(float(np.max(c)), cmax(200.0, p), rel_tol=1e-4)


def test_auc_matches_analytic() -> None:
    p = _params()
    t = np.linspace(0.0, 300.0, 300_001)  # fully decayed by 300 h at ke ~= 0.14
    c = np.asarray(concentration_single(t, 200.0, p))
    numeric_auc = float(np.trapezoid(c, t))
    assert math.isclose(numeric_auc, auc(200.0, p), rel_tol=1e-3)


def test_superposition_linearity() -> None:
    p = _params()
    t = np.linspace(0.0, 24.0, 1000)
    single = np.asarray(concentration_single(t, 100.0, p))
    double = np.asarray(concentration_single(t, 200.0, p))
    assert np.allclose(double, 2.0 * single)


def test_curve_is_sum_of_shifted_intakes() -> None:
    p = _params()
    t = np.linspace(0.0, 24.0, 1000)
    intakes = [(0.0, 100.0), (4.0, 80.0)]
    curve = concentration_curve(t, intakes, p)
    manual = np.asarray(concentration_single(t, 100.0, p)) + np.asarray(
        concentration_single(t - 4.0, 80.0, p)
    )
    assert np.allclose(curve, manual)


def test_curve_masks_future_intake() -> None:
    p = _params()
    t = np.linspace(0.0, 3.0, 300)  # all before the intake at t = 5 h
    curve = concentration_curve(t, [(5.0, 100.0)], p)
    assert np.all(curve == 0.0)


def test_monotonic_decay_after_tmax() -> None:
    p = _params()
    tm = tmax_h(p)
    t = np.linspace(tm + 0.01, 36.0, 4000)
    c = np.asarray(concentration_single(t, 200.0, p))
    assert np.all(np.diff(c) <= 0.0)  # non-increasing
    assert c[0] > c[-1]  # and strictly lower overall


def test_ka_equals_ke_uses_limiting_form() -> None:
    p = _params(ka=1.0, ke=1.0)  # exact singularity
    t = np.linspace(0.0, 10.0, 1000)
    c = np.asarray(concentration_single(t, 100.0, p))
    expected = p.F * 100.0 * p.ka_per_h / p.V_l * t * np.exp(-p.ka_per_h * t)
    assert np.all(np.isfinite(c))
    assert np.allclose(c, expected)


def test_near_singularity_is_continuous() -> None:
    # The general branch (ka != ke) should approach the limiting form as ka -> ke.
    p_near = _params(ka=1.0 + 1e-4, ke=1.0)
    p_limit = _params(ka=1.0, ke=1.0)
    t = np.linspace(0.1, 10.0, 500)
    c_near = np.asarray(concentration_single(t, 100.0, p_near))
    c_limit = np.asarray(concentration_single(t, 100.0, p_limit))
    assert np.allclose(c_near, c_limit, rtol=1e-3, atol=1e-6)


def test_invalid_params_raise() -> None:
    with pytest.raises(ValueError):
        tmax_h(_params(v=0.0))
    with pytest.raises(ValueError):
        concentration_single(1.0, 100.0, _params(ka=0.0))
