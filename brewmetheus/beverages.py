from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Beverage:
    """One row of the caffeine catalog."""

    key: str
    name: str
    default_serving_ml: float
    caffeine_mg: float  # at default_serving_ml
    note: str | None = None  # deadpan tasting note, shown under the beverage picker

    @property
    def caffeine_mg_per_ml(self) -> float:
        return self.caffeine_mg / self.default_serving_ml


# Caffeine values are per the default serving and sit within cited real-world ranges.
# The compound drinks are defined so their math is honest: a red-eye is drip + one
# espresso shot, a dead eye is drip + three.
BEVERAGES: dict[str, Beverage] = {
    b.key: b
    for b in (
        Beverage("espresso", "Espresso", 30.0, 63.0),
        Beverage("drip_coffee", "Drip / Americano", 240.0, 95.0),
        Beverage("instant_coffee", "Instant coffee", 240.0, 62.0),
        Beverage("black_tea", "Black tea", 240.0, 47.0),
        Beverage("green_tea", "Green tea", 240.0, 28.0),
        Beverage("cola", "Cola", 330.0, 34.0),
        Beverage("energy_drink", "Energy drink", 250.0, 80.0),
        Beverage(
            "cold_brew",
            "Cold brew",
            350.0,
            205.0,
            note="Steeped 18 h. Higher yield than the color implies.",
        ),
        Beverage(
            "pour_over",
            "Pour-over (V60)",
            240.0,
            113.0,
            note="Drip coffee, but you watched.",
        ),
        Beverage(
            "ristretto",
            "Ristretto",
            20.0,
            63.0,
            note="Same grounds, less water, more opinions.",
        ),
        Beverage(
            "red_eye",
            "Red-eye (drip + 1 shot)",
            270.0,
            158.0,
            note="For when a single service instance isn't enough.",
        ),
        Beverage(
            "dead_eye",
            "Dead Eye (drip + 3 shots)",
            330.0,
            284.0,
            note="Escalation path of last resort.",
        ),
        Beverage(
            "decaf",
            "Decaf",
            240.0,
            3.0,
            note="Filed under water.",
        ),
        Beverage(
            "death_wish",
            "Death Wish (12 oz)",
            350.0,
            300.0,
            note="One cup is 75% of the default daily cap.",
        ),
    )
}


def caffeine_for(beverage_key: str, serving_ml: float | None = None) -> float:
    """Caffeine (mg) for a beverage, optionally scaled to a custom serving.

    Linear in volume: a double espresso has ~twice the caffeine. Uses the
    beverage's default serving when ``serving_ml`` is None.
    """
    try:
        beverage = BEVERAGES[beverage_key]
    except KeyError as exc:
        raise KeyError(f"Unknown beverage key: {beverage_key!r}") from exc
    if serving_ml is None:
        return beverage.caffeine_mg
    if serving_ml < 0:
        raise ValueError("serving_ml must be non-negative.")
    return beverage.caffeine_mg_per_ml * serving_ml
