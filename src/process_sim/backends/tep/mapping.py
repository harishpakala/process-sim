"""Raw TEP variable names and stable engineering metadata.

Indices are intentionally 1-based because they match the reference Fortran
and ProfBraatz APIs. This module is the first place where raw TEP variables
are given platform-facing semantic names; the scientific backend itself is
not modified.
"""

MEASUREMENT_NAMES = {
    1: "a_feed_flow",
    2: "d_feed_flow",
    3: "e_feed_flow",
    4: "a_c_feed_flow",
    5: "recycle_flow",
    6: "reactor_feed_rate",
    7: "reactor_pressure",
    8: "reactor_level",
    9: "reactor_temperature",
    10: "purge_rate",
    11: "separator_temperature",
    12: "separator_level",
    13: "separator_pressure",
    14: "separator_underflow",
    15: "stripper_level",
    16: "stripper_pressure",
    17: "stripper_underflow",
    18: "stripper_temperature",
    19: "stripper_steam_flow",
    20: "compressor_work",
    21: "reactor_cooling_water_outlet_temperature",
    22: "separator_cooling_water_outlet_temperature",
}

# Engineering units from the ProfBraatz/TEP reference documentation.
# Composition analyzers XMEAS23-XMEAS41 are reported in mol%.
MEASUREMENT_UNITS = {
    1: "kscmh",
    2: "kg/hr",
    3: "kg/hr",
    4: "kscmh",
    5: "kscmh",
    6: "kscmh",
    7: "kPa gauge",
    8: "%",
    9: "deg C",
    10: "kscmh",
    11: "deg C",
    12: "%",
    13: "kPa gauge",
    14: "m3/hr",
    15: "%",
    16: "kPa gauge",
    17: "m3/hr",
    18: "deg C",
    19: "kg/hr",
    20: "kW",
    21: "deg C",
    22: "deg C",
    23: "mol%",
    24: "mol%",
    25: "mol%",
    26: "mol%",
    27: "mol%",
    28: "mol%",
    29: "mol%",
    30: "mol%",
    31: "mol%",
    32: "mol%",
    33: "mol%",
    34: "mol%",
    35: "mol%",
    36: "mol%",
    37: "mol%",
    38: "mol%",
    39: "mol%",
    40: "mol%",
    41: "mol%",
}

MANIPULATED_VARIABLE_NAMES = {
    1: "d_feed_flow",
    2: "e_feed_flow",
    3: "a_feed_flow",
    4: "a_c_feed_flow",
    5: "compressor_recycle_valve",
    6: "purge_valve",
    7: "separator_pot_liquid_flow",
    8: "stripper_liquid_product_flow",
    9: "stripper_steam_valve",
    10: "reactor_cooling_water_flow",
    11: "condenser_cooling_water_flow",
    12: "agitator_speed",
}

DISTURBANCE_NAMES = {
    1: "a_c_feed_ratio_step",
    2: "b_composition_step",
    3: "d_feed_temperature_step",
    4: "reactor_cooling_water_inlet_temperature_step",
    5: "condenser_cooling_water_inlet_temperature_step",
    6: "a_feed_loss_step",
    7: "c_header_pressure_loss_step",
    8: "a_b_c_feed_composition_random",
    9: "d_feed_temperature_random",
    10: "c_feed_temperature_random",
    11: "reactor_cooling_water_inlet_temperature_random",
    12: "condenser_cooling_water_inlet_temperature_random",
    13: "reaction_kinetics_slow_drift",
    14: "reactor_cooling_water_valve_sticking",
    15: "condenser_cooling_water_valve_sticking",
}


def raw_measurement_name(index: int) -> str:
    """Return the reference name, e.g. ``XMEAS9``."""
    if not 1 <= index <= 41:
        raise IndexError("XMEAS index must be in the range 1..41")
    return f"XMEAS{index}"


def raw_manipulated_variable_name(index: int) -> str:
    """Return the reference name, e.g. ``XMV10``."""
    if not 1 <= index <= 12:
        raise IndexError("XMV index must be in the range 1..12")
    return f"XMV{index}"


def raw_disturbance_name(index: int) -> str:
    """Return the reference name, e.g. ``IDV6``."""
    if not 1 <= index <= 20:
        raise IndexError("IDV index must be in the range 1..20")
    return f"IDV{index}"
