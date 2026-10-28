"""Season 3 digital range-ruler geometry (October 2026).

The measured 59 mm ruler / 34 mm pitch dimensions and the FFB-style
"between" convention are documented in docs/season3-acceptance.md.
This implementation uses integer square/strip intersection, not a raster line
or a copied implementation from another game engine.
"""

RULER_WIDTH_MM = 59
PITCH_SQUARE_MM = 34


def under_interception_ruler(origin, landing, square):
    """Positive overlap with the ruler, strictly between its two endpoints.

    "Between" means that the candidate's centre is nearer to each endpoint
    than the endpoints are to each other (the FFB digital convention). The
    perpendicular projection of the entire square, not only its centre, must
    overlap the ruler strip. Squaring the comparison keeps all edges exact and
    invariant under translation, reflection, rotation and pass reversal.
    The virtual ruler follows the actual landing square after scatter.
    """
    dx, dy = landing.x - origin.x, landing.y - origin.y
    x, y = square.x - origin.x, square.y - origin.y
    length_squared = dx * dx + dy * dy
    if not length_squared or x * x + y * y >= length_squared:
        return False
    if (x - dx) ** 2 + (y - dy) ** 2 >= length_squared:
        return False
    # Twice the square's minimum perpendicular distance, before dividing by
    # the length of the pass. Its projected half-extent is (|dx|+|dy|)/2.
    gap = max(0, 2 * abs(dx * y - dy * x) - abs(dx) - abs(dy))
    return (gap * PITCH_SQUARE_MM) ** 2 < RULER_WIDTH_MM ** 2 * length_squared
