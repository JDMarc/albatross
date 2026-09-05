"""Theme-derived thermal display chrome, separate from diagnostic colors."""


def _blend(start, end, amount):
    return tuple(round(a + (b - a) * amount) for a, b in zip(start, end))


def thermal_chrome(colors):
    """Derive dark display surfaces and linework from the active HUD palette.

    Heat scores, unavailable readings and fluid-path colors never pass through
    this palette. Derive it at draw time so changing themes needs no view reset.
    """
    background, bright, glow, _fault = colors
    field = _blend((0, 0, 0), background, .5)
    return {
        "panel": _blend((0, 0, 0), background, .64),
        "field": field,
        "surface": _blend(field, glow, .07),
        "component": _blend(field, glow, .14),
        "shadow": _blend((0, 0, 0), background, .25),
        "raster": _blend(field, glow, .035),
        "grid": _blend(field, glow, .07),
        "sweep": _blend(field, glow, .14),
        "centerline": _blend(field, glow, .23),
        "ticks": _blend(field, glow, .40),
        "edge": _blend(field, glow, .72),
        "ink": _blend(glow, bright, .40),
        "muted": glow,
        "bright": bright,
    }
