from __future__ import annotations

import math

from brewmetheus.models import PKParams, UserProfile

# Half-life modifiers (multiplicative). See the plan's defaults table.
SMOKING_HALF_LIFE_FACTOR = 0.5  # CYP1A2 induction -> faster clearance
ORAL_CONTRACEPTIVE_HALF_LIFE_FACTOR = 2.0  # CYP1A2 inhibition -> slower clearance
PREGNANCY_HALF_LIFE_FACTOR = 2.5  # markedly slower (third trimester up to ~15 h)

_LN2 = math.log(2.0)


def effective_half_life_h(profile: UserProfile) -> float:
    """Baseline half-life scaled by the active lifestyle / physiology modifiers."""
    half_life = profile.base_half_life_h
    if profile.smoker:
        half_life *= SMOKING_HALF_LIFE_FACTOR
    if profile.oral_contraceptives:
        half_life *= ORAL_CONTRACEPTIVE_HALF_LIFE_FACTOR
    if profile.pregnant:
        half_life *= PREGNANCY_HALF_LIFE_FACTOR
    return half_life


def derive_params(profile: UserProfile) -> PKParams:
    """Map a user profile to model-ready PK parameters.

    weight -> V (vertical scaling); half-life modifiers -> ke (shape and timing).
    Fails loud on non-physical inputs so pk_model never receives bad parameters.
    """
    if profile.weight_kg <= 0:
        raise ValueError("weight_kg must be positive.")
    if profile.base_half_life_h <= 0:
        raise ValueError("base_half_life_h must be positive.")
    if profile.ka_per_h <= 0:
        raise ValueError("ka_per_h must be positive.")
    if profile.bioavailability <= 0:
        raise ValueError("bioavailability must be positive.")
    if profile.vd_per_kg <= 0:
        raise ValueError("vd_per_kg must be positive.")

    half_life = effective_half_life_h(profile)
    return PKParams(
        F=profile.bioavailability,
        V_l=profile.vd_per_kg * profile.weight_kg,
        ka_per_h=profile.ka_per_h,
        ke_per_h=_LN2 / half_life,
        effective_half_life_h=half_life,
    )
