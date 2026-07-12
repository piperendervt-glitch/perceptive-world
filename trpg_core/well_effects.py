"""Pure LOD-to-effect policy for the goblin scenario's old well."""

from enum import Enum


class WellEffectTier(Enum):
    NONE = "none"
    MINOR = "minor"
    NORMAL = "normal"
    MAXIMUM = "maximum"


_TIERS = (
    WellEffectTier.NONE, WellEffectTier.MINOR,
    WellEffectTier.NORMAL, WellEffectTier.MAXIMUM,
)


def well_effect_tier_for_lod(current_lod: int) -> WellEffectTier:
    if type(current_lod) is not int or not 0 <= current_lod <= 3:
        raise ValueError("well effect LOD must be an int from 0 through 3")
    return _TIERS[current_lod]


def well_physical_damage_bonus_for_lod(current_lod: int) -> int:
    well_effect_tier_for_lod(current_lod)
    return current_lod
