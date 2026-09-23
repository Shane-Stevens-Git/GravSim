"""Scene construction: the default scene (and later presets, save/load)."""
from body import Body
from config import *
from physics import circular_speed


def make_scene(sun_cfg, sun_fixed=False):
    """A sun (mass, radius, color, kind) plus a demo planet on an ellipse."""
    mass, radius, color, kind = sun_cfg
    sun = Body((WIDTH / 2, HEIGHT / 2), mass, radius, color, fixed=sun_fixed, kind=kind,
               name="Sun")
    r0 = max(220, radius * 4)
    v0 = 0.85 * circular_speed(sun.mass, r0)
    planet = Body((sun.pos.x + r0, sun.pos.y), mass=20, radius=8,
                  color=(90, 170, 255), vel=(0, -v0), name="Planet")
    if not sun.fixed:   # zero total momentum so the system doesn't drift
        sun.vel = -planet.vel * planet.mass / sun.mass
    return [sun, planet]
