"""Shared CAN calibration selectors for ECU map/profile requests."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FuelProfile:
    name: str
    code: int
    fuel_table: int
    stoich_afr: float


FUEL_PROFILES: tuple[FuelProfile, ...] = (
    FuelProfile("87", 0, 0, 14.70),
    FuelProfile("91", 1, 0, 14.70),
    FuelProfile("93", 2, 0, 14.70),
    FuelProfile("100", 3, 1, 14.70),
    FuelProfile("E85", 4, 2, 9.85),
    FuelProfile("C16", 5, 3, 14.77),
)


FUEL_PROFILE_BY_CODE = {profile.code: profile for profile in FUEL_PROFILES}
FUEL_PROFILE_BY_NAME = {profile.name: profile for profile in FUEL_PROFILES}


def fuel_profile_for_code(fuel_code: int) -> FuelProfile:
    return FUEL_PROFILE_BY_CODE.get(fuel_code, FUEL_PROFILE_BY_NAME["93"])


def spark_table_for_mode(mode_code: int) -> int:
    """Return 0 for the initial spark map, 1 for SPORT+ performance timing."""
    return 1 if mode_code >= 3 else 0
