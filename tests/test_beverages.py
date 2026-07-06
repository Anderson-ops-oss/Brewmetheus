import pytest

from brewmetheus.beverages import BEVERAGES, caffeine_for


def test_keys_are_consistent() -> None:
    for key, beverage in BEVERAGES.items():
        assert beverage.key == key


def test_reference_values() -> None:
    assert caffeine_for("espresso") == 63.0
    assert caffeine_for("drip_coffee") == 95.0
    assert caffeine_for("energy_drink") == 80.0


def test_caffeine_scales_linearly_with_serving() -> None:
    single = caffeine_for("espresso")  # 30 ml default
    assert caffeine_for("espresso", serving_ml=60.0) == pytest.approx(2.0 * single)
    assert caffeine_for("espresso", serving_ml=15.0) == pytest.approx(0.5 * single)


def test_per_ml_property() -> None:
    espresso = BEVERAGES["espresso"]
    assert espresso.caffeine_mg_per_ml == pytest.approx(63.0 / 30.0)


_NEW_KEYS = (
    "cold_brew",
    "pour_over",
    "ristretto",
    "red_eye",
    "dead_eye",
    "decaf",
    "death_wish",
)


def test_new_beverages_present() -> None:
    for key in _NEW_KEYS:
        assert key in BEVERAGES


def test_compound_drinks_have_honest_math() -> None:
    drip = caffeine_for("drip_coffee")
    shot = caffeine_for("espresso")
    assert caffeine_for("red_eye") == pytest.approx(drip + shot)  # drip + 1 shot
    assert caffeine_for("dead_eye") == pytest.approx(drip + 3 * shot)  # drip + 3 shots


def test_notes_default_none_but_new_skus_carry_them() -> None:
    assert BEVERAGES["espresso"].note is None  # original rows unchanged
    assert BEVERAGES["decaf"].note is not None
    assert all(BEVERAGES[key].note for key in _NEW_KEYS)


def test_unknown_beverage_raises() -> None:
    with pytest.raises(KeyError):
        caffeine_for("unicorn_latte")


def test_negative_serving_raises() -> None:
    with pytest.raises(ValueError):
        caffeine_for("espresso", serving_ml=-10.0)
