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


def test_unknown_beverage_raises() -> None:
    with pytest.raises(KeyError):
        caffeine_for("unicorn_latte")


def test_negative_serving_raises() -> None:
    with pytest.raises(ValueError):
        caffeine_for("espresso", serving_ml=-10.0)
