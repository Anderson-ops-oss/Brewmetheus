import math
import pytest
from brewmetheus.models import UserProfile
from brewmetheus.params import (
    ORAL_CONTRACEPTIVE_HALF_LIFE_FACTOR,
    PREGNANCY_HALF_LIFE_FACTOR,
    SMOKING_HALF_LIFE_FACTOR,
    derive_params,
)
from brewmetheus.pk_model import tmax_h


def test_default_profile_maps_to_baseline() -> None:
    p = derive_params(UserProfile())
    assert p.F == 1.0
    assert math.isclose(p.V_l, 35.0)  # 0.5 L/kg * 70 kg
    assert math.isclose(p.effective_half_life_h, 5.0)
    assert math.isclose(p.ke_per_h, math.log(2) / 5.0)
    assert p.ka_per_h == 6.0


def test_weight_scales_volume_linearly() -> None:
    light = derive_params(UserProfile(weight_kg=55.0))
    heavy = derive_params(UserProfile(weight_kg=110.0))
    assert math.isclose(heavy.V_l, 2.0 * light.V_l)  # double weight -> double V
    assert math.isclose(light.ke_per_h, heavy.ke_per_h)  # weight must not touch elimination


def test_smoking_halves_half_life() -> None:
    base = derive_params(UserProfile())
    smoker = derive_params(UserProfile(smoker=True))
    assert math.isclose(
        smoker.effective_half_life_h,
        base.effective_half_life_h * SMOKING_HALF_LIFE_FACTOR,
    )
    # shorter half-life => larger ke (faster clearance)
    assert math.isclose(smoker.ke_per_h, base.ke_per_h / SMOKING_HALF_LIFE_FACTOR)


def test_oral_contraceptives_lengthen_half_life() -> None:
    base = derive_params(UserProfile())
    oc = derive_params(UserProfile(oral_contraceptives=True))
    assert math.isclose(
        oc.effective_half_life_h,
        base.effective_half_life_h * ORAL_CONTRACEPTIVE_HALF_LIFE_FACTOR,
    )


def test_pregnancy_lengthens_half_life() -> None:
    base = derive_params(UserProfile())
    preg = derive_params(UserProfile(pregnant=True))
    assert math.isclose(
        preg.effective_half_life_h,
        base.effective_half_life_h * PREGNANCY_HALF_LIFE_FACTOR,
    )


def test_modifiers_combine_multiplicatively() -> None:
    # smoker (x0.5) and oral contraceptives (x2.0) cancel -> baseline half-life
    p = derive_params(UserProfile(smoker=True, oral_contraceptives=True))
    assert math.isclose(p.effective_half_life_h, UserProfile().base_half_life_h)


def test_defaults_give_realistic_peak_time() -> None:
    # ka=6, ke~0.14 should peak around 40 minutes (~0.64 h)
    p = derive_params(UserProfile())
    assert 0.5 < tmax_h(p) < 0.8


@pytest.mark.parametrize(
    "profile",
    [
        UserProfile(weight_kg=0.0),
        UserProfile(base_half_life_h=0.0),
        UserProfile(ka_per_h=0.0),
        UserProfile(bioavailability=0.0),
        UserProfile(vd_per_kg=0.0),
    ],
)
def test_invalid_profile_raises(profile: UserProfile) -> None:
    with pytest.raises(ValueError):
        derive_params(profile)
