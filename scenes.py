"""Scenes: preset scenarios, and saving/loading a scene to JSON.

A scene is a plain dict:
    bodies        list of Body
    sun           index of the main body (sun panel / HUD reference)
    target        index of the body the camera follows (None = fixed camera)
    center, zoom  camera (center used when the camera is fixed)
    lagrange      (primary index, secondary index) to mark L1-L5, or None
    mode          collision mode to switch to, or None to keep the current one
"""
import json
import math
import os
import random

import pygame

from body import Body
from craft import make_craft, pilot_from_dict, pilot_to_dict
from config import *
from physics import circular_speed, corotating_velocity, lagrange_points  # noqa: F401 (re-exported)

SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saves")
QUICKSAVE = os.path.join(SAVE_DIR, "quicksave.json")
CENTER = pygame.Vector2(WIDTH / 2, HEIGHT / 2)

YELLOW = (255, 200, 60)
ROCK = (160, 160, 160)


def scene(bodies, sun=0, target=0, center=None, zoom=1.0, lagrange=None, mode=None):
    return {"bodies": bodies, "sun": sun, "target": target,
            "center": pygame.Vector2(center if center is not None else CENTER),
            "zoom": zoom, "lagrange": lagrange, "mode": mode}


def zero_momentum(bodies):
    """Shift velocities so total momentum is zero (the system won't drift)."""
    movers = [b for b in bodies if not b.fixed]
    total_m = sum(b.mass for b in movers)
    if total_m <= 0:
        return
    p = sum((b.vel * b.mass for b in movers), pygame.Vector2())
    for b in movers:
        b.vel -= p / total_m


def orbiting(primary, dist, angle_deg, mass, radius, color, name, speed_factor=1.0,
             screen_ccw=False, particle=False):
    """A body on a circular orbit (times speed_factor) around `primary`."""
    offset = pygame.Vector2(dist, 0).rotate(angle_deg)
    tangent = offset.rotate(-90 if screen_ccw else 90).normalize()   # y points down
    v = circular_speed(primary.mass + mass, dist) * speed_factor
    return Body(primary.pos + offset, mass, radius, color,
                vel=primary.vel + tangent * v, name=name, particle=particle)


def make_sun(sun_cfg, fixed=False, pos=None):
    mass, radius, color, kind = sun_cfg
    return Body(pos if pos is not None else CENTER, mass, radius, color,
                fixed=fixed, kind=kind, name="Sun")


# --- Scenarios --------------------------------------------------------------------
def sun_and_planet(sun_cfg, sun_fixed=False):
    """The default scene: a sun plus a planet on an elliptical orbit."""
    sun = make_sun(sun_cfg, sun_fixed)
    r0 = max(220, sun.radius * 4)
    planet = orbiting(sun, r0, 0, 20, 8, (90, 170, 255), "Planet", speed_factor=0.85,
                      screen_ccw=True)
    bodies = [sun, planet]
    if not sun.fixed:
        zero_momentum(bodies)
    return scene(bodies)


def inner_solar_system(sun_cfg, sun_fixed=False):
    """Four planets and a moon. Masses are far bigger (relative to the sun)
    than the real ones so their pulls are visible, so the spacing was tuned
    to stay stable: the Moon sits well inside Earth's Hill sphere."""
    sun = make_sun(sun_cfg, sun_fixed)
    earth = orbiting(sun, 220, 200, 80, 6, (80, 160, 255), "Earth", screen_ccw=True)
    moon = orbiting(earth, 13, 0, 0.3, 2, (210, 210, 220), "Moon", screen_ccw=True)
    bodies = [
        sun,
        orbiting(sun, 75, 30, 1.5, 4, (180, 170, 160), "Mercury", screen_ccw=True),
        orbiting(sun, 130, 110, 8, 6, (235, 200, 140), "Venus", screen_ccw=True),
        earth, moon,
        orbiting(sun, 340, 320, 4, 5, (230, 110, 70), "Mars", screen_ccw=True),
    ]
    if not sun.fixed:
        zero_momentum(bodies)
    return scene(bodies, zoom=0.95)


def binary_star(sun_cfg=None, sun_fixed=False):
    """Two equal stars orbiting each other, plus a planet circling both."""
    m, sep = 6000, 160
    v = math.sqrt(G * m / (2 * sep))              # each star's speed around the barycenter
    a = Body(CENTER + (-sep / 2, 0), m, 22, (255, 190, 90), vel=(0, v), kind="star",
             name="Star A")
    b = Body(CENTER + (sep / 2, 0), m, 18, (255, 120, 80), vel=(0, -v), kind="star",
             name="Star B")
    vp = circular_speed(2 * m, 420)
    planet = Body(CENTER + (0, -420), 30, 8, (90, 170, 255), vel=(-vp, 0), name="Planet")
    return scene([a, b, planet], sun=0, target=None, zoom=0.75)


def figure_eight(sun_cfg=None, sun_fixed=False):
    """Three equal masses chasing each other along a figure-8
    (Chenciner & Montgomery, 2000). Beautiful, and only marginally stable."""
    m, L = 3000, 220
    vs = math.sqrt(G * m / L)                     # velocity scale for G=m=L=1 units
    x1 = pygame.Vector2(-0.97000436, 0.24308753)
    v3 = pygame.Vector2(-0.93240737, -0.86473146)
    specs = [(x1, -v3 / 2, (255, 200, 60), "Star A"),
             (-x1, -v3 / 2, (120, 180, 255), "Star B"),
             (pygame.Vector2(0, 0), v3, (255, 120, 90), "Star C")]
    bodies = [Body(CENTER + p * L, m, 12, c, vel=v * vs, kind="star", name=n)
              for p, v, c, n in specs]
    return scene(bodies, sun=0, target=None, zoom=1.0)


def asteroid_belt(sun_cfg, sun_fixed=False, n=300, seed=7):
    """A sun, a Jupiter-like giant and a belt of asteroids inside its orbit.
    Asteroids near the giant's 2:1 resonance (~227 px, where they orbit exactly
    twice per giant orbit) get pumped every pass - over time (try 8x speed)
    that part of the belt is stirred up, like the Kirkwood gaps."""
    rng = random.Random(seed)
    sun = make_sun(sun_cfg, sun_fixed)
    giant = orbiting(sun, 360, 0, 100, 14, (230, 170, 100), "Giant", screen_ccw=True)
    bodies = [sun, giant]
    for i in range(n):
        d = rng.uniform(165, 265)
        bodies.append(orbiting(sun, d, rng.uniform(0, 360), 0.2, 2, ROCK, f"Asteroid {i + 1}",
                               speed_factor=rng.uniform(0.97, 1.03), screen_ccw=True,
                               particle=True))
    if not sun.fixed:
        zero_momentum(bodies)
    return scene(bodies, zoom=0.9)


def lagrange(sun_cfg, sun_fixed=False):
    """Sun + gas giant with asteroids at all five Lagrange points.

    L4/L5 (60 deg ahead of / behind the giant) are stable: asteroids placed
    there stay, and ones nudged a few degrees away trace 'tadpole' loops
    around them (easiest to see with the camera following the giant). L1, L2
    and L3 are balance points on a knife edge: those asteroids drift away.
    Probes at L1 and L2 show the fix real spacecraft use: small thruster burns
    (station-keeping) keep them there while the asteroids beside them drift off.
    The sun must be free here - L-points are defined for two bodies orbiting
    their shared center of mass. Giant/sun mass ratio 1.5% is well inside
    the L4/L5 stability limit (3.85%).
    """
    sun = make_sun(sun_cfg, fixed=False)
    giant = orbiting(sun, 260, 0, 150, 13, (230, 170, 100), "Giant", screen_ccw=True)
    bodies = [sun, giant]
    zero_momentum(bodies)
    for label, p in lagrange_points(sun, giant).items():
        stable = label in ("L4", "L5")
        for deg in ((0, -6, 6, -12, 12) if stable else (0,)):
            pos = sun.pos + (p - sun.pos).rotate(deg)    # slide along the orbit
            bodies.append(Body(pos, 0.05, 2, (200, 220, 255) if stable else (255, 150, 150),
                               vel=corotating_velocity(sun, giant, pos),
                               name=f"{label} asteroid", particle=True))
    points = lagrange_points(sun, giant)
    for label in ("L1", "L2"):             # probes holding the two unstable points nearest the giant
        probe = make_craft(Body(points[label], 0.001, 4, (225, 232, 255),
                                vel=corotating_velocity(sun, giant, points[label]),
                                name=f"{label} probe"))
        probe.pilot.set_mode("hold", hold=("L", sun, giant, label))
        bodies.append(probe)
    return scene(bodies, lagrange=(0, 1), zoom=1.0)


def galaxy_collision(sun_cfg=None, sun_fixed=False, seed=11):
    """Two disk galaxies on a close, bound fly-by, in the spirit of Toomre &
    Toomre (1972): each galaxy is a heavy core plus a disk of test-particle
    stars. Tides from the passing core fling out long tails and bridges;
    the cores swing back and eventually merge."""
    rng = random.Random(seed)
    m1, m2 = 20_000, 12_000
    total = m1 + m2
    mu = G * total
    dist, peri = 750.0, 200.0
    # Bound encounter: start at 70% of escape speed, so after the first pass
    # the galaxies swing back (~30 s later) and eventually merge. Solve for
    # the sideways offset (impact parameter b) that gives closest approach `peri`.
    v = 0.7 * math.sqrt(2 * mu / dist)
    energy = v * v / 2 - mu / dist
    a_axis = -mu / (2 * energy)

    def periapsis(b):
        e = math.sqrt(max(0.0, 1 + 2 * energy * (b * v) ** 2 / mu ** 2))
        return a_axis * (1 - e)

    lo, hi = 0.0, dist
    for _ in range(60):                     # periapsis grows with b: bisect
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if periapsis(mid) < peri else (lo, mid)
    sin_a = lo / dist
    rel_pos = pygame.Vector2(dist, 0)                           # core2 - core1
    rel_vel = pygame.Vector2(-v * math.sqrt(1 - sin_a ** 2), -v * sin_a)
    rel_pos, rel_vel = rel_pos.rotate(-20), rel_vel.rotate(-20)
    # Cores: supermassive black holes with softened gravity (a galaxy's
    # central mass is spread out), so stars passing close aren't slingshot away.
    c1 = Body(CENTER - rel_pos * (m2 / total), m1, 4, (0, 0, 0),
              vel=-rel_vel * (m2 / total), kind="blackhole", name="Core A", soft=GALAXY_CORE_SOFT,
              absorbs=False)
    c2 = Body(CENTER + rel_pos * (m1 / total), m2, 3, (0, 0, 0),
              vel=rel_vel * (m1 / total), kind="blackhole", name="Core B", soft=GALAXY_CORE_SOFT,
              absorbs=False)
    bodies = [c1, c2]
    # Disks rotate the same way as the encounter (prograde) - that's what
    # makes the dramatic tails.
    spin_ccw = (rel_pos.x * rel_vel.y - rel_pos.y * rel_vel.x) < 0
    for core, n, r_max, color in ((c1, GALAXY_STARS[0], 160, (170, 200, 255)),
                                  (c2, GALAXY_STARS[1], 125, (255, 220, 160))):
        eps2 = (core.soft ** 2 + SOFTENING ** 2) / 2          # pair softening
        for k in range(n):
            d = 22 + (r_max - 22) * math.sqrt(rng.random())      # uniform over the disk
            offset = pygame.Vector2(d, 0).rotate(rng.uniform(0, 360))
            # circular speed for the *softened* pull: v^2 = G M r^2 / (r^2 + eps^2)^1.5
            v = math.sqrt(G * core.mass * d * d / (d * d + eps2) ** 1.5)
            tangent = offset.rotate(-90 if spin_ccw else 90).normalize()
            bodies.append(Body(core.pos + offset, 0.001, 1, color, vel=core.vel + tangent * v,
                               name=f"{core.name[-1]} star", particle=True))
    return scene(bodies, sun=0, target=None, zoom=0.5)


def shatter_demo(sun_cfg, sun_fixed=False):
    """Destruction on a timer (switches to SHATTER mode):
    ~2 s  a planet and a gas giant on opposite (head-on) orbits collide at
          ~3x their mutual escape speed and fragment;
    ~3.5 s a second planet on a sun-grazing orbit dips inside the sun's
          Roche limit and is torn into a debris stream.
    Bonus: the head-on hit cancels most of the remnant's orbital speed, so it
    falls sunward and gets shredded by tides too."""
    sun = make_sun(sun_cfg, sun_fixed)
    r = 200
    planet = orbiting(sun, r, 0, 20, 8, (90, 170, 255), "Planet", screen_ccw=True)
    giant = orbiting(sun, r, 180, 200, 14, (230, 170, 100), "Rogue giant", screen_ccw=False)
    # Grazing orbit: apoapsis 320 px, periapsis 40 px (Roche limit ~57 px).
    ra, rp = 320.0, 40.0
    v_apo = math.sqrt(2 * G * sun.mass * rp / (ra * (ra + rp)))
    # Starts at the top so its sun-grazing pass happens on the far side from
    # where the smash wreckage falls.
    comet = orbiting(sun, ra, 270, 20, 8, (140, 230, 200), "Doomed planet",
                     speed_factor=v_apo / circular_speed(sun.mass + 20, ra), screen_ccw=True)
    bodies = [sun, planet, giant, comet]
    if not sun.fixed:
        zero_momentum(bodies)
    return scene(bodies, mode="shatter")


SCENARIOS = [
    ("Sun & planet", "The default: one planet on an elliptical orbit.", sun_and_planet),
    ("Inner solar system", "Four planets, and a moon around Earth.", inner_solar_system),
    ("Binary star", "Two stars orbiting each other, a planet circling both.", binary_star),
    ("Figure-eight", "Three stars chasing each other along a figure-8.", figure_eight),
    ("Asteroid belt", "300 asteroids and a giant that stirs them up.", asteroid_belt),
    ("Lagrange points", "Asteroids at L1-L5; probes hold L1 and L2 with thrusters.", lagrange),
    ("Galaxy collision", "Two disk galaxies fly past and tear out tidal tails.", galaxy_collision),
    ("Shatter demo", "A head-on smash, then tides shred what falls sunward.", shatter_demo),
]


# --- Save / load ------------------------------------------------------------------
def to_dict(sc, extra=None):
    bodies = sc["bodies"]

    def idx(b):
        return bodies.index(b) if b in bodies else None

    data = {
        "format": "gravsim-scene", "version": 1,
        "sun": sc["sun"] if isinstance(sc["sun"], int) else idx(sc["sun"]),
        "target": sc["target"] if isinstance(sc["target"], int) or sc["target"] is None
        else idx(sc["target"]),
        "center": [sc["center"].x, sc["center"].y],
        "zoom": sc["zoom"], "lagrange": sc["lagrange"], "mode": sc["mode"],
        "bodies": [{
            "name": b.name, "pos": [b.pos.x, b.pos.y], "vel": [b.vel.x, b.vel.y],
            "mass": b.mass, "radius": b.radius, "color": list(b.color),
            "fixed": b.fixed, "kind": b.kind, "particle": b.particle, "soft": b.soft,
            "absorbs": b.absorbs, "heading": b.heading,
            "pilot": pilot_to_dict(b.pilot, idx) if b.pilot else None,
        } for b in bodies],
    }
    data.update(extra or {})
    return data


def from_dict(data):
    if data.get("format") != "gravsim-scene":
        raise ValueError("not a GravSim scene file")
    records = data["bodies"]
    bodies = [Body(d["pos"], d["mass"], d["radius"], d["color"], vel=d["vel"],
                   fixed=d.get("fixed", False), kind=d.get("kind", "body"),
                   name=d.get("name", "Body"), particle=d.get("particle", False),
                   soft=d.get("soft", SOFTENING), absorbs=d.get("absorbs", True))
              for d in records]
    for b, d in zip(bodies, records):         # spacecraft: restore autopilots
        b.heading = d.get("heading", b.heading)
        if d.get("pilot"):
            b.pilot = pilot_from_dict(d["pilot"], bodies)
    sc = scene(bodies, sun=data.get("sun", 0) or 0, target=data.get("target"),
               center=data.get("center"), zoom=data.get("zoom", 1.0),
               lagrange=tuple(data["lagrange"]) if data.get("lagrange") else None,
               mode=data.get("mode", "merge"))
    sc["sim_time"] = data.get("sim_time", 0.0)
    return sc


def save_file(data, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def load_file(path):
    with open(path) as f:
        return from_dict(json.load(f))


def ask_path(save):
    """Native save/open dialog (tkinter). Returns a path, or None if cancelled.
    Falls back to the quicksave file if dialogs aren't available."""
    os.makedirs(SAVE_DIR, exist_ok=True)
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return QUICKSAVE
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    types = [("GravSim scene", "*.json"), ("All files", "*.*")]
    try:
        if save:
            path = filedialog.asksaveasfilename(parent=root, initialdir=SAVE_DIR,
                                                initialfile="scene.json",
                                                defaultextension=".json", filetypes=types)
        else:
            path = filedialog.askopenfilename(parent=root, initialdir=SAVE_DIR, filetypes=types)
    finally:
        root.destroy()
    return path or None


# --- Spawn tools --------------------------------------------------------------------
def ring_around(center, bodies, n=RING_PARTICLES, seed=None):
    """A ring of test particles on circular orbits around `center`.
    Returns (new particles, message). Kept inside ~40% of the Hill sphere
    when `center` itself orbits something heavier."""
    from physics import dominant_body, hill_radius
    rng = random.Random(seed)
    r_in = center.radius + 3
    r_out = max(center.radius * 3, r_in + 40)
    primary = dominant_body(center, bodies)
    if primary is not None:
        r_out = min(r_out, 0.45 * hill_radius(center, primary))
        if r_out < r_in + 4:
            return [], f"{center.name} is too light to hold a ring here (Hill sphere too small)"
    ring = [orbiting(center, rng.uniform(r_in, r_out), rng.uniform(0, 360), 0.01, 1,
                     RING_COLOR, f"{center.name} ring", screen_ccw=True, particle=True)
            for _ in range(n)]
    return ring, f"Added a ring of {n} particles around {center.name}"


def place_in_orbit(point, bodies, mass, radius, color, name, reverse=False):
    """A new body at `point` on a circular orbit around whatever pulls hardest
    there. Returns (body or None, primary)."""
    from physics import strongest_pull_at
    primary = strongest_pull_at(point, bodies)
    if primary is None or point.distance_to(primary.pos) <= primary.radius + radius:
        return None, primary
    offset = point - primary.pos
    return orbiting(primary, offset.length(), math.degrees(math.atan2(offset.y, offset.x)),
                    mass, radius, color, name, screen_ccw=not reverse), primary
