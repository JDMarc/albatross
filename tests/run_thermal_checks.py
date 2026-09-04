"""Dependency-free thermal regression runner."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_thermal import (
    test_all_requested_simulation_scenarios_feed_common_model,
    test_can_aggregator_includes_thermal_snapshot_and_alerts,
    test_piecewise_normalization_and_safe_effectiveness,
    test_protocol_propagates_fault_instead_of_fake_zero,
    test_shared_config_has_32_contiguous_channels,
)


if __name__ == "__main__":
    checks = (
        test_shared_config_has_32_contiguous_channels,
        test_piecewise_normalization_and_safe_effectiveness,
        test_protocol_propagates_fault_instead_of_fake_zero,
        test_all_requested_simulation_scenarios_feed_common_model,
        test_can_aggregator_includes_thermal_snapshot_and_alerts,
    )
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
