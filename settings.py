"""Live physics settings (the Physics tab of the controls panel).

Every module does `from config import *`, so each has its own copy of the
constants. Changing a setting writes the new value into every loaded module
that has it, so the change takes effect immediately everywhere.
"""
import math
import sys

import config

MODULES = ("config", "physics", "body", "craft", "scenes", "app", "effects", "field",
           "sound", "history")

# key, label, low, high, log scale?, display format
SPECS = [
    ("G", "Gravity strength (G)", 100.0, 2000.0, True, "{:.0f}"),
    ("SOFTENING", "Softening", 0.5, 10.0, True, "{:.1f} px"),
    ("PHYSICS_RATE", "Physics steps", 120.0, 960.0, True, "{:.0f} /s"),
    ("TRAIL_LENGTH", "Trail length", 30.0, 1200.0, True, "{:.0f} frames"),
    ("RESTITUTION", "Bounciness (bounce mode)", 0.0, 1.0, False, "{:.2f}"),
    ("SHATTER_ENERGY", "Shatter threshold", 0.2, 5.0, True, "{:.2f}"),
    ("ROCHE_COEFF", "Roche coefficient", 0.3, 2.44, False, "{:.2f}"),
    ("LAUNCH_SCALE", "Throw strength", 0.25, 4.0, True, "{:.2f}x"),
]
_SPEC = {s[0]: s for s in SPECS}


def get(key):
    if key == "PHYSICS_RATE":
        return 1.0 / config.PHYSICS_DT
    return getattr(config, key)


def set(key, value):
    if key == "PHYSICS_RATE":
        key, value = "PHYSICS_DT", 1.0 / value
    elif key == "TRAIL_LENGTH":
        value = int(round(value))
    for name in MODULES:
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, key):
            setattr(mod, key, value)


DEFAULTS = {key: get(key) for key, *_ in SPECS}


def reset():
    for key, value in DEFAULTS.items():
        set(key, value)


def to_t(key):
    """Current value -> slider position 0..1."""
    _, _, lo, hi, log, _ = _SPEC[key]
    v = min(max(get(key), lo), hi)
    return math.log(v / lo) / math.log(hi / lo) if log else (v - lo) / (hi - lo)


def from_t(key, t):
    _, _, lo, hi, log, _ = _SPEC[key]
    return lo * (hi / lo) ** t if log else lo + (hi - lo) * t


def rows():
    """(key, label, value text, slider position, changed?) for the UI."""
    return [(key, label, fmt.format(get(key)), to_t(key),
             abs(get(key) - DEFAULTS[key]) > 1e-9 * max(1.0, abs(DEFAULTS[key])))
            for key, label, _, _, _, fmt in SPECS]
