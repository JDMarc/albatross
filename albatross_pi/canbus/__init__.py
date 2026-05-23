"""CAN bus utilities for the Albatross HUD."""
from .ids import ArduinoToEcuID, ECUToHudID, ArduinoToHudID, PiToArduinoID, PiToEcuID, SystemCommandID
from .decode import CANStateAggregator
from .iface import SocketCANInterface
from .encode import (
    build_boost_target_frame,
    build_ecu_fuel_profile_frame,
    build_ecu_rev_limiter_strategy_frame,
    build_ecu_spark_table_frame,
    build_engine_run_switch_frame,
    build_fuel_type_frame,
    build_limp_mode_frame,
    build_media_control_frame,
    build_mode_selection_frame,
    build_nfc_auth_frame,
    build_phone_link_frame,
    build_traction_level_frame,
)

__all__ = [
    "ECUToHudID",
    "ArduinoToHudID",
    "ArduinoToEcuID",
    "PiToArduinoID",
    "PiToEcuID",
    "SystemCommandID",
    "CANStateAggregator",
    "SocketCANInterface",
    "build_boost_target_frame",
    "build_ecu_fuel_profile_frame",
    "build_ecu_rev_limiter_strategy_frame",
    "build_ecu_spark_table_frame",
    "build_engine_run_switch_frame",
    "build_fuel_type_frame",
    "build_limp_mode_frame",
    "build_media_control_frame",
    "build_mode_selection_frame",
    "build_nfc_auth_frame",
    "build_phone_link_frame",
    "build_traction_level_frame",
]
