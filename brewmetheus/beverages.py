from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Beverage:
    """One row of the caffeine catalog."""

    key: str
    name: str
    default_serving_ml: float
    caffeine_mg: float  # at default_serving_ml

    @property
    def caffeine_mg_per_ml(self) -> float:
        return self.caffeine_mg / self.default_serving_ml


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
