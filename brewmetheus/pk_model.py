from __future__ import annotations
import math
from collections.abc import Iterable
import numpy as np
from numpy.typing import ArrayLike, NDArray
from brewmetheus.models import PKParams

FloatArray = NDArray[np.float64]

# Below this |ka - ke| (per hour) the Bateman formula is numerically unstable
# (cancellation + division by a small number), so we switch to the analytic
# limiting form. Default parameters (ka ~= 6, ke ~= 0.14) never approach this.
_KA_KE_EPS = 1e-6


def _validate(params: PKParams) -> None:
    """Guard against non-physical parameters that would divide by zero."""
    if params.V_l <= 0 or params.ka_per_h <= 0 or params.ke_per_h <= 0 or params.F <= 0:
        raise ValueError("PKParams must have positive F, V_l, ka_per_h, ke_per_h.")


def _bateman(t: FloatArray, dose_mg: float, params: PKParams) -> FloatArray:
    """Vectorized single-dose concentration; contribution is 0 for t < 0.

    Internal kernel: assumes ``t`` is a float ndarray and ``params`` is valid.
    """
    ka = params.ka_per_h
    ke = params.ke_per_h
    prefactor = params.F * dose_mg / params.V_l
    # Compute on the clamped time so exp() never sees a large positive argument.
    t_pos = np.maximum(t, 0.0)
    if abs(ka - ke) < _KA_KE_EPS:
        conc = prefactor * ka * t_pos * np.exp(-ka * t_pos)
    else:
        conc = prefactor * ka / (ka - ke) * (np.exp(-ke * t_pos) - np.exp(-ka * t_pos))
    conc = np.where(t < 0.0, 0.0, conc)
    return np.asarray(conc, dtype=np.float64)


def concentration_single(t_h: ArrayLike, dose_mg: float, params: PKParams) -> float | FloatArray:
    """Plasma concentration (mg/L) of a single dose at elapsed time ``t_h``.

    Accepts a scalar or an array; returns the matching shape. ``t_h`` is elapsed
    time since the dose, so negative values (before the dose) yield 0.
    """
    _validate(params)
    t = np.asarray(t_h, dtype=np.float64)
    conc = _bateman(t, dose_mg, params)
    if t.ndim == 0:
        return float(conc)
    return conc


def concentration_curve(
    times_h: ArrayLike,
    intakes: Iterable[tuple[float, float]],
    params: PKParams,
) -> FloatArray:
    """Superposed concentration of many intakes evaluated on ``times_h``.

    ``intakes`` is a list of ``(t_offset_h, dose_mg)`` sharing one ``params``.
    Linear PK => the total curve is the sum of each dose's shifted single curve.
    """
    _validate(params)
    times = np.asarray(times_h, dtype=np.float64)
    total = np.zeros_like(times)
    for t_i, dose_i in intakes:
        total = total + _bateman(times - t_i, dose_i, params)
    return np.asarray(total, dtype=np.float64)


def tmax_h(params: PKParams) -> float:
    """Time of peak concentration for a single dose (analytic)."""
    _validate(params)
    ka = params.ka_per_h
    ke = params.ke_per_h
    if abs(ka - ke) < _KA_KE_EPS:
        return 1.0 / ka
    return math.log(ka / ke) / (ka - ke)


def cmax(dose_mg: float, params: PKParams) -> float:
    """Peak concentration (mg/L) for a single dose."""
    _validate(params)
    peak = _bateman(np.asarray(tmax_h(params), dtype=np.float64), dose_mg, params)
    return float(peak)


def auc(dose_mg: float, params: PKParams) -> float:
    """Total exposure of a single dose: AUC = F * D / (V * ke) (analytic)."""
    _validate(params)
    return params.F * dose_mg / (params.V_l * params.ke_per_h)
