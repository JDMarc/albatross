"""Cylinder fins stay inset on both banks of the thermal schematic."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from albatross_pi.hud.thermal_architecture import cylinder_geometry


def _cross(a, b, point):
    return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])


def _inside_distances(polygon, point):
    """Signed distances to each edge, positive inside either winding."""
    winding = 1 if _cross(polygon[0], polygon[1], polygon[2]) > 0 else -1
    return [
        winding * _cross(a, b, point) / math.dist(a, b)
        for a, b in zip(polygon, polygon[1:] + polygon[:1])
    ]


def check():
    banks = {side: cylinder_geometry(side) for side in ("LEFT", "RIGHT")}
    for side, (polygon, fins) in banks.items():
        polygon = list(polygon)
        assert len(polygon) == 4, (side, "expected a four-corner cylinder bank")
        assert len(fins) >= 5, (side, "too few cooling fins")
        assert all(math.isfinite(v) for point in polygon for v in point)
        edges = list(zip(polygon, polygon[1:] + polygon[:1]))
        assert all(math.dist(a, b) > 0 for a, b in edges)
        turns = [_cross(polygon[i], polygon[(i + 1) % 4], polygon[(i + 2) % 4]) for i in range(4)]
        assert all(turn > 0 for turn in turns) or all(turn < 0 for turn in turns), (side, "bank must be convex")
        # Relative to the narrow bank dimension, fins must remain substantial.
        minimum_span = min(math.dist(a, b) for a, b in edges) * .45
        assert len(set(tuple(tuple(point) for point in fin) for fin in fins)) == len(fins)
        for start, end in fins:
            assert all(math.isfinite(v) for point in (start, end) for v in point)
            assert math.dist(start, end) >= minimum_span, (side, "fin does not span the bank")
            for endpoint in (start, end):
                assert min(_inside_distances(polygon, endpoint)) >= .5, (side, "fin endpoint lacks an inset margin", endpoint)
            for step in range(21):
                fraction = step / 20
                point = tuple(a + (b - a) * fraction for a, b in zip(start, end))
                assert min(_inside_distances(polygon, point)) >= -1e-9, (side, "fin leaves cylinder", point)

    left_polygon, left_fins = banks["LEFT"]
    right_polygon, right_fins = banks["RIGHT"]
    assert len(left_fins) == len(right_fins)
    left_points = list(left_polygon) + [point for fin in left_fins for point in fin]
    right_points = list(right_polygon) + [point for fin in right_fins for point in fin]
    for left, right in zip(left_points, right_points):
        assert math.isclose(right[0], 1000 - left[0], abs_tol=1e-9)
        assert math.isclose(right[1], left[1], abs_tol=1e-9)
    print("Thermal cylinder geometry checks passed.")


if __name__ == "__main__":
    check()
