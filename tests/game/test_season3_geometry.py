"""Independent polygon oracle for the pinned Season 3 digital ruler model."""
import math

import pytest

from botbowl import Square
from botbowl.core.geometry import under_interception_ruler


def clipped_square_area(dx, dy, x, y):
    # Clip the candidate square against the two sides of a physical strip.
    # This floating-point polygon construction is independent of the engine's
    # integer distance inequality. Dimensions are pinned in the acceptance doc.
    polygon = [(x - .5, y - .5), (x + .5, y - .5),
               (x + .5, y + .5), (x - .5, y + .5)]
    half_width = (59 / 34) / 2
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    for sign in (-1, 1):
        output = []
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            da = half_width - sign * (nx * a[0] + ny * a[1])
            db = half_width - sign * (nx * b[0] + ny * b[1])
            if da >= 0:
                output.append(a)
            if (da >= 0) != (db >= 0):
                t = da / (da - db)
                output.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        polygon = output
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(polygon, polygon[1:] + polygon[:1]))) / 2


@pytest.mark.parametrize('dx,dy', [(x, y) for x in range(14) for y in range(14) if x or y])
def test_ruler_matches_independent_polygon_clipping_for_all_range_vectors(dx, dy):
    origin, landing = Square(0, 0), Square(dx, dy)
    length = math.hypot(dx, dy)
    for x in range(-2, dx + 3):
        for y in range(-2, dy + 3):
            between = math.hypot(x, y) < length and math.hypot(x - dx, y - dy) < length
            expected = between and clipped_square_area(dx, dy, x, y) > 1e-10
            assert under_interception_ruler(origin, landing, Square(x, y)) == expected, (dx, dy, x, y)


@pytest.mark.parametrize('dx,dy', [(4, 0), (0, 4), (2, 8), (8, 3), (11, 7), (13, 1)])
def test_ruler_is_invariant_under_pass_reversal_reflection_rotation_and_translation(dx, dy):
    for x in range(-2, dx + 3):
        for y in range(-2, dy + 3):
            expected = under_interception_ruler(Square(0, 0), Square(dx, dy), Square(x, y))
            for a, b, c, d in [(dx, dy, x, y), (dy, dx, y, x)]:
                for sx, sy in [(1, 1), (-1, 1), (1, -1), (-1, -1)]:
                    origin = Square(15, 15)
                    landing = Square(15 + sx * a, 15 + sy * b)
                    candidate = Square(15 + sx * c, 15 + sy * d)
                    assert under_interception_ruler(origin, landing, candidate) == expected
                    assert under_interception_ruler(landing, origin, candidate) == expected


@pytest.mark.parametrize('origin,landing,candidate,expected', [
    ((0, 0), (0, 0), (0, 0), False),
    ((0, 0), (4, 0), (0, 1), False),  # Equal/further from the landing endpoint.
    ((0, 0), (4, 0), (4, 1), False),
    ((0, 0), (4, 0), (2, 1), True),  # Whole-square overlap, not centre-only.
    ((0, 0), (4, 0), (2, 2), False),
    ((0, 0), (4, 8), (3, 2), False),  # Supplied diagonal exclusion.
    ((0, 0), (8, 3), (4, 3), True),  # Whole-square overlap on an oblique pass.
])
def test_ruler_boundary_examples(origin, landing, candidate, expected):
    assert under_interception_ruler(Square(*origin), Square(*landing), Square(*candidate)) == expected
