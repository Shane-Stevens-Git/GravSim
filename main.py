"""GravSim - a 2D interactive gravity sandbox.

Real inverse-square n-body gravity. Pick a body type (1-5), fine-tune
its size/mass with the scroll wheel, then click-drag-release to throw it.
Bodies orbit, collide (merge or bounce), or get flung out of the scene.
"""
import math
import random
from collections import deque

import numpy as np
import pygame

import ui

# --- Window / timing -------------------------------------------------------
WIDTH, HEIGHT = 1280, 800
FPS = 60
BG_COLOR = (8, 10, 20)

# --- Physics -----------------------------------------------------------------
# Units: distance in pixels, time in seconds, mass in arbitrary "mass units".
G = 500.0
PHYSICS_DT = 1 / 240        # fixed physics step (s), independent of frame rate
MAX_FRAME_TIME = 0.05       # don't try to "catch up" more than this after a stall
SOFTENING = 5.0             # px; avoids infinite force if r -> 0
CULL_DISTANCE = 4000        # px from view center; farther bodies are deleted
RESTITUTION = 0.8           # bounciness in bounce mode (1 = perfectly elastic)

# --- Launch controls -----------------------------------------------------------
LAUNCH_SCALE = 1.0          # launch speed (px/s) per pixel dragged
SLINGSHOT = False           # False: drag the way it should go. True: pull back like a slingshot.
PREVIEW_STEPS = 320         # trajectory preview length (steps of PREVIEW_DT)
PREVIEW_DT = 1 / 40
PREVIEW_MAX_BODIES = 12     # preview only simulates the heaviest bodies (for speed)
SCROLL_STEP = 1.15          # size/mass multiplier per scroll notch
SIZE_RANGE = (0.3, 4.0)
MASS_RANGE = (0.05, 20.0)

# --- Trails ------------------------------------------------------------------
TRAIL_LENGTH = 240          # frames of history per body (4 s at 60 fps)
SUN_TRAIL_LENGTH = 900      # the sun moves slowly, so it keeps a longer trail (15 s)
TRAIL_BANDS = 8             # fade is drawn in this many brightness bands

# Body presets, selected with number keys 1-5: (name, mass, radius, color)
PRESETS = [
    ("Asteroid",   1,     3, (160, 160, 160)),
    ("Moon",       5,     5, (210, 210, 220)),
    ("Planet",     20,    8, (90, 170, 255)),
    ("Gas giant",  200,  14, (230, 170, 100)),
    ("Red dwarf",  2000, 20, (255, 110, 70)),
]


# Sun types for the sun panel: (name, mass, radius, color, kind)
SUN_TYPES = [
    ("Red dwarf",   4_000,  22, (255, 120, 80),  "star"),
    ("Yellow star", 10_000, 30, (255, 200, 60),  "star"),
    ("Blue giant",  25_000, 45, (150, 185, 255), "star"),
    ("White dwarf", 8_000,  10, (235, 240, 255), "star"),
    ("Black hole",  40_000, 12, (0, 0, 0),       "blackhole"),
]
DEFAULT_SUN = 1
SUN_MASS_RANGE = (1_000, 100_000)   # sun panel slider (log scale)
SUN_RADIUS_RANGE = (5, 80)
BLACK_HOLE_RING = ui.BLACK_HOLE_RING

# --- Camera -------------------------------------------------------------------
ZOOM_RANGE = (0.1, 5.0)
ZOOM_STEP = 1.15            # zoom factor per Ctrl+scroll notch or +/- press


class View:
    """Camera: which world point sits at the screen center, and the zoom."""

    def __init__(self):
        self.screen_center = pygame.Vector2(WIDTH / 2, HEIGHT / 2)
        self.center = pygame.Vector2(self.screen_center)
        self.zoom = 1.0

    def to_screen(self, p):
        return (pygame.Vector2(p) - self.center) * self.zoom + self.screen_center

    def to_world(self, s):
        return (pygame.Vector2(s) - self.screen_center) / self.zoom + self.center

    def zoom_by(self, factor, screen_pos=None):
        """Zoom, keeping the world point under screen_pos fixed on screen."""
        new = min(max(self.zoom * factor, ZOOM_RANGE[0]), ZOOM_RANGE[1])
        if screen_pos is not None:
            anchor = self.to_world(screen_pos)
            self.center = anchor - (pygame.Vector2(screen_pos) - self.screen_center) / new
        self.zoom = new


class Body:
    """A circular mass in the simulation."""

    _glow_cache = {}

    def __init__(self, pos, mass, radius, color, vel=(0, 0), fixed=False, kind="body"):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.mass = float(mass)
        self.radius = int(radius)
        self.color = tuple(int(c) for c in color)
        self.fixed = fixed  # fixed ("pinned") bodies pull on others but never move
        self.kind = kind    # "body", "star" or "blackhole" (affects drawing only)
        self.trail = deque(maxlen=TRAIL_LENGTH)

    @property
    def accent(self):
        """Color for glow and trail - a black hole uses its glowing ring."""
        return BLACK_HOLE_RING if self.kind == "blackhole" else self.color

    @classmethod
    def glow_surface(cls, radius, color):
        """Soft translucent halo, cached per (radius, color)."""
        key = (radius, color)
        if key not in cls._glow_cache:
            if len(cls._glow_cache) > 500:
                cls._glow_cache.clear()
            size = radius * 6
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            c = radius * 3
            for i, alpha in enumerate((18, 30, 45)):
                pygame.draw.circle(surf, (*color, alpha), (c, c), int(radius * (2.6 - i * 0.5)))
            cls._glow_cache[key] = surf
        return cls._glow_cache[key]

    def draw(self, surface, view):
        p = view.to_screen(self.pos)
        cx, cy = round(p.x), round(p.y)
        r = max(1, round(self.radius * view.zoom))
        if not (-r * 3 < cx < WIDTH + r * 3 and -r * 3 < cy < HEIGHT + r * 3):
            return
        if 2 <= r <= 120:
            surface.blit(self.glow_surface(r, self.accent), (cx - r * 3, cy - r * 3))
        if self.kind == "blackhole":
            pygame.draw.circle(surface, BLACK_HOLE_RING, (cx, cy),
                               r + max(2, r // 4), max(1, r // 6))
            pygame.draw.circle(surface, (0, 0, 0), (cx, cy), r)
        else:
            pygame.draw.circle(surface, self.color, (cx, cy), r)

    def draw_trail(self, surface, view, offset=(0.0, 0.0)):
        """Fading line through recent positions (oldest = dimmest).
        `offset` is added to stored points (used for sun-relative trails)."""
        n = len(self.trail)
        if n < 2:
            return
        ox, oy = offset
        z = view.zoom
        cx, cy = view.center
        sx, sy = view.screen_center
        pts = [((x + ox - cx) * z + sx, (y + oy - cy) * z + sy) for x, y in self.trail]
        for band in range(TRAIL_BANDS):
            a = band * (n - 1) // TRAIL_BANDS
            b = (band + 1) * (n - 1) // TRAIL_BANDS + 1
            if b - a < 2:
                continue
            t = 0.65 * (band + 1) / TRAIL_BANDS
            col = [int(bg + (c - bg) * t) for bg, c in zip(BG_COLOR, self.accent)]
            pygame.draw.lines(surface, col, False, pts[a:b])


# --- Physics -----------------------------------------------------------------
def accelerations(pos, mass):
    """N-body gravity: a_i = sum_j G*m_j * (p_j - p_i) / |p_j - p_i|^3."""
    d = pos[None, :, :] - pos[:, None, :]           # d[i, j] = p_j - p_i
    dist_sq = (d * d).sum(axis=-1) + SOFTENING ** 2
    inv_r3 = dist_sq ** -1.5
    np.fill_diagonal(inv_r3, 0.0)                   # no self-attraction
    return G * (d * (mass[None, :] * inv_r3)[:, :, None]).sum(axis=1)


def pack(bodies):
    """Body objects -> NumPy arrays."""
    pos = np.array([(b.pos.x, b.pos.y) for b in bodies], dtype=float).reshape(-1, 2)
    vel = np.array([(b.vel.x, b.vel.y) for b in bodies], dtype=float).reshape(-1, 2)
    mass = np.array([b.mass for b in bodies], dtype=float)
    movable = np.array([0.0 if b.fixed else 1.0 for b in bodies])[:, None]
    return pos, vel, mass, movable


def verlet(pos, vel, acc, mass, movable, dt):
    """One velocity-Verlet step, in place. Returns the new accelerations."""
    pos += movable * (vel * dt + 0.5 * acc * dt * dt)
    new_acc = accelerations(pos, mass)
    vel += movable * (0.5 * (acc + new_acc) * dt)
    return new_acc


def find_collisions(pos, vel, radii, mode):
    """Index pairs (i, j), i < j, of overlapping bodies.

    In bounce mode only pairs still moving toward each other count, so a
    pair that has already bounced isn't hit again while separating.
    """
    d = pos[None, :, :] - pos[:, None, :]
    dist = np.hypot(d[..., 0], d[..., 1])
    hit = dist < (radii[:, None] + radii[None, :])
    if mode == "bounce":
        approaching = ((vel[None, :, :] - vel[:, None, :]) * d).sum(axis=-1) < 0
        hit &= approaching
    i, j = np.nonzero(np.triu(hit, k=1))
    return list(zip(i.tolist(), j.tolist()))


def merge(a, b):
    """Perfectly inelastic collision: b is absorbed into a.

    Conserves mass and momentum; the merged body sits at the combined
    center of mass and keeps the combined volume (radius^3 adds up).
    """
    m = a.mass + b.mass
    if a.fixed or b.fixed:
        anchor = a if a.fixed else b
        a.pos.update(anchor.pos)
        a.vel.update(0, 0)
        a.fixed = True
    else:
        a.pos = (a.pos * a.mass + b.pos * b.mass) / m
        a.vel = (a.vel * a.mass + b.vel * b.mass) / m
    if a.kind == "blackhole" or b.kind == "blackhole":
        a.kind, a.color = "blackhole", (0, 0, 0)     # anything + black hole = black hole
    else:
        a.color = tuple(int((ca * a.mass + cb * b.mass) / m) for ca, cb in zip(a.color, b.color))
    a.radius = max(2, round((a.radius ** 3 + b.radius ** 3) ** (1 / 3)))
    a.mass = m


def bounce(a, b):
    """Collision with restitution: impulse along the line of centers,
    plus pushing the bodies apart so they no longer overlap."""
    inv_a = 0.0 if a.fixed else 1.0 / a.mass
    inv_b = 0.0 if b.fixed else 1.0 / b.mass
    if inv_a + inv_b == 0:
        return
    delta = b.pos - a.pos
    dist = delta.length()
    n = delta / dist if dist > 1e-9 else pygame.Vector2(1, 0)
    rel = (b.vel - a.vel).dot(n)
    if rel < 0:
        j = -(1 + RESTITUTION) * rel / (inv_a + inv_b)
        a.vel -= n * (j * inv_a)
        b.vel += n * (j * inv_b)
    overlap = a.radius + b.radius - dist
    if overlap > 0:
        a.pos -= n * (overlap * inv_a / (inv_a + inv_b))
        b.pos += n * (overlap * inv_b / (inv_a + inv_b))


def simulate(bodies, dt, steps, mode):
    """Advance `steps` fixed steps, handling collisions. Mutates `bodies`."""
    done = 0
    while done < steps and bodies:
        pos, vel, mass, movable = pack(bodies)
        radii = np.array([b.radius for b in bodies], dtype=float)
        acc = accelerations(pos, mass)
        pairs = []
        while done < steps and not pairs:
            acc = verlet(pos, vel, acc, mass, movable, dt)
            done += 1
            pairs = find_collisions(pos, vel, radii, mode)
        for b, p, v in zip(bodies, pos, vel):
            b.pos.update(p[0], p[1])
            b.vel.update(v[0], v[1])
        if not pairs:
            break
        # Resolve collisions in Python, then repack and keep going.
        gone = set()
        for i, j in pairs:
            if i in gone or j in gone:
                continue
            a, b = bodies[i], bodies[j]
            if mode == "merge":
                if b.mass > a.mass:          # heavier body survives
                    a, b = b, a
                    i, j = j, i
                merge(a, b)
                gone.add(j)
            else:
                bounce(a, b)
        if gone:
            bodies[:] = [b for k, b in enumerate(bodies) if k not in gone]


def predict_path(bodies, start, vel0, frame_body=None, test_radius=0):
    """Preview a throw: a massless test particle flown through the n-body
    system (the heaviest bodies move during the preview too).

    If frame_body is given (the body the camera follows), the path is
    returned relative to it, so it matches what you see on screen.
    """
    heavy = sorted(bodies, key=lambda b: b.mass, reverse=True)[:PREVIEW_MAX_BODIES]
    if frame_body is not None and frame_body not in heavy:
        heavy.append(frame_body)
    k = heavy.index(frame_body) if frame_body is not None else None
    pos, vel, mass, movable = pack(heavy)
    radii = np.array([b.radius for b in heavy], dtype=float)
    frame0 = pos[k].copy() if k is not None else None
    pos = np.vstack([pos, start])
    vel = np.vstack([vel, vel0])
    mass = np.append(mass, 0.0)
    movable = np.vstack([movable, [[1.0]]])
    acc = accelerations(pos, mass)
    points = []
    for i in range(PREVIEW_STEPS):
        acc = verlet(pos, vel, acc, mass, movable, PREVIEW_DT)
        p = pos[-1].copy()
        if (np.hypot(*(pos[:-1] - p).T) < radii + test_radius).any():
            break                                   # would hit something
        if k is not None:
            p -= pos[k] - frame0
        if i % 3 == 0:
            points.append(p)
    return points


def orbit_info(rel_pos, rel_vel, central_mass, impact_radius):
    """Two-body orbit a launch would produce around `central_mass`.

    Returns eccentricity, whether the orbit escapes (energy >= 0), and
    whether its closest approach is inside `impact_radius`.
    """
    mu = G * central_mass
    r = rel_pos.length()
    v2 = rel_vel.length_squared()
    if r < 1e-6:
        return None
    energy = v2 / 2 - mu / r
    e_vec = ((v2 - mu / r) * rel_pos - rel_pos.dot(rel_vel) * rel_vel) / mu
    e = e_vec.length()
    if energy >= 0:
        return {"e": e, "escape": True, "impact": False}
    a = -mu / (2 * energy)
    periapsis = a * (1 - e)
    return {"e": e, "escape": False, "impact": periapsis < impact_radius}


def circular_speed(central_mass, r):
    """Speed needed for a circular orbit of radius r: v = sqrt(G*M/r)."""
    return (G * central_mass / max(r, 1e-6)) ** 0.5


# --- Rendering helpers --------------------------------------------------------
def make_starfield(n=250):
    bg = pygame.Surface((WIDTH, HEIGHT))
    bg.fill(BG_COLOR)
    rng = random.Random(42)
    for _ in range(n):
        b = rng.randint(60, 180)
        bg.set_at((rng.randrange(WIDTH), rng.randrange(HEIGHT)), (b, b, b))
    return bg


def draw_arrow(surface, start, end, color):
    pygame.draw.line(surface, color, start, end, 2)
    d = pygame.Vector2(end) - pygame.Vector2(start)
    if d.length() < 8:
        return
    d.scale_to_length(10)
    pygame.draw.polygon(surface, color, [end, end + d.rotate(150), end + d.rotate(-150)])


def make_scene(sun_cfg, sun_fixed=False):
    """A sun (mass, radius, color, kind) plus a demo planet on an ellipse."""
    mass, radius, color, kind = sun_cfg
    sun = Body((WIDTH / 2, HEIGHT / 2), mass, radius, color, fixed=sun_fixed, kind=kind)
    r0 = max(220, radius * 4)
    v0 = 0.85 * circular_speed(sun.mass, r0)
    planet = Body((sun.pos.x + r0, sun.pos.y), mass=20, radius=8,
                  color=(90, 170, 255), vel=(0, -v0))
    if not sun.fixed:   # zero total momentum so the system doesn't drift
        sun.vel = -planet.vel * planet.mass / sun.mass
    return [sun, planet]


class App:
    """Owns the simulation state, input handling and drawing."""

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("GravSim")
        self.clock = pygame.time.Clock()
        self.hud = ui.HUD(WIDTH, HEIGHT)
        self.background = make_starfield()
        self.view = View()

        self.preset_idx = 2         # start on "Planet"
        self.size_mult = self.mass_mult = 1.0
        self.drag_start = None      # screen position of mouse-down while aiming
        self.slider = None          # (name, track rect) while dragging a slider
        self.show_preview = True
        self.show_trails = True
        self.follow = True          # camera keeps the sun centered
        self.mode = "merge"         # collision mode: "merge" or "bounce"
        self.paused = False
        self.running = True
        self.accumulator = 0.0
        self.sim_time = 0.0
        _name, *cfg = SUN_TYPES[DEFAULT_SUN]
        self.reset(tuple(cfg), fixed=False)

    # --- State helpers -----------------------------------------------------------
    @property
    def following(self):
        return self.follow and self.sun in self.bodies

    def set_sun(self, body):
        """Make `body` the main body (camera target, sun panel, HUD reference)."""
        self.sun = body
        body.trail = deque(maxlen=SUN_TRAIL_LENGTH)

    def reset(self, sun_cfg=None, fixed=None):
        """Restart the scene, keeping the current sun settings by default."""
        if sun_cfg is None:
            sun_cfg = (self.sun.mass, self.sun.radius, self.sun.color, self.sun.kind)
        if fixed is None:
            fixed = self.sun.fixed
        self.bodies = make_scene(sun_cfg, fixed)
        self.set_sun(self.bodies[0])
        self.view.center = pygame.Vector2(self.sun.pos)
        self.sim_time = 0.0

    def clear_trails(self):
        for b in self.bodies:
            b.trail.clear()

    def select_preset(self, i):
        self.preset_idx = i
        self.size_mult = self.mass_mult = 1.0

    def selected(self):
        name, mass, radius, color = PRESETS[self.preset_idx]
        r = max(2, round(radius * self.size_mult))
        m = mass * self.size_mult ** 3 * self.mass_mult   # size keeps density; Shift changes it
        return name, m, r, color

    def launch_velocity(self, mouse):
        """Drag vector -> velocity. Measured in world pixels, so a drag means
        the same speed at every zoom level (the arrow = ~1 s of travel)."""
        v = (pygame.Vector2(mouse) - self.drag_start) * (LAUNCH_SCALE / self.view.zoom)
        return -v if SLINGSHOT else v

    def zoom(self, factor, screen_pos=None):
        # While following, the sun is locked to the center, so zoom about it.
        self.view.zoom_by(factor, None if self.following else screen_pos)

    # --- Sun controls --------------------------------------------------------------
    def sun_type_index(self):
        s = self.sun
        for i, (_n, m, r, c, kind) in enumerate(SUN_TYPES):
            if (abs(s.mass - m) < 0.5 and s.radius == r and s.kind == kind
                    and (kind == "blackhole" or s.color == c)):
                return i
        return None

    def apply_sun_type(self, i):
        _name, m, r, c, kind = SUN_TYPES[i]
        s = self.sun
        s.mass, s.radius, s.color, s.kind = float(m), r, c, kind

    def recenter(self):
        """Shift the whole system so the sun sits at the view center, at rest.
        This is only a change of reference frame - relative motion is kept."""
        if self.sun not in self.bodies:
            return
        shift = self.view.center - self.sun.pos
        v = pygame.Vector2(self.sun.vel)
        for b in self.bodies:
            b.pos += shift
            if not b.fixed:
                b.vel -= v
        self.clear_trails()

    def update_slider(self, pos):
        name, track = self.slider
        t = min(max((pos[0] - track.x) / track.width, 0.0), 1.0)
        if name == "sun_mass":
            lo, hi = SUN_MASS_RANGE
            self.sun.mass = float(f"{lo * (hi / lo) ** t:.3g}")   # 3 significant figures
        elif name == "sun_radius":
            lo, hi = SUN_RADIUS_RANGE
            self.sun.radius = round(lo + (hi - lo) * t)

    # --- Input ---------------------------------------------------------------------
    def handle_key(self, k):
        if k == pygame.K_ESCAPE:
            self.running = False
        elif k == pygame.K_SPACE:
            self.paused = not self.paused
        elif k == pygame.K_h:
            self.hud.show_help = not self.hud.show_help
        elif k == pygame.K_s:
            self.hud.sun_collapsed = not self.hud.sun_collapsed
        elif k == pygame.K_t:
            self.show_preview = not self.show_preview
        elif k == pygame.K_l:
            self.show_trails = not self.show_trails
            self.clear_trails()
        elif k == pygame.K_m:
            self.mode = "bounce" if self.mode == "merge" else "merge"
        elif k == pygame.K_v:
            self.follow = not self.follow
            self.clear_trails()                 # old trails were in the old frame
        elif k == pygame.K_f:
            if self.sun in self.bodies:
                self.sun.fixed = not self.sun.fixed
                self.sun.vel.update(0, 0)
        elif k == pygame.K_c:
            self.bodies = [b for b in self.bodies if b is self.sun]
        elif k == pygame.K_r:
            self.reset()
        elif k in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self.zoom(ZOOM_STEP)
        elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.zoom(1 / ZOOM_STEP)
        elif k in (pygame.K_0, pygame.K_KP0):
            self.view.zoom = 1.0
        elif pygame.K_1 <= k < pygame.K_1 + len(PRESETS):
            self.select_preset(k - pygame.K_1)

    def handle_action(self, action, ref, pos):
        """A click on a UI element (see ui.HUD.add)."""
        kind, arg = action
        if kind == "key":
            self.handle_key(arg)
        elif kind == "preset":
            self.select_preset(arg)
        elif kind == "sun_type":
            self.apply_sun_type(arg)
        elif kind == "sun_recenter":
            self.recenter()
        elif kind == "slider":
            self.slider = (arg, ref)
            self.update_slider(pos)

    def throw(self, pos):
        _, m, r, color = self.selected()
        vel = self.launch_velocity(pos)
        if self.following:                      # throw relative to the sun's motion
            vel += self.sun.vel
        self.bodies.append(Body(self.view.to_world(self.drag_start), m, r, color, vel=vel))
        self.drag_start = None

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self.handle_key(event.key)
            elif event.type == pygame.MOUSEWHEEL:
                mods = pygame.key.get_mods()
                if mods & pygame.KMOD_CTRL:
                    self.zoom(ZOOM_STEP ** event.y, pygame.mouse.get_pos())
                else:
                    f = SCROLL_STEP ** event.y
                    if mods & pygame.KMOD_SHIFT:
                        self.mass_mult = min(max(self.mass_mult * f, MASS_RANGE[0]), MASS_RANGE[1])
                    else:
                        self.size_mult = min(max(self.size_mult * f, SIZE_RANGE[0]), SIZE_RANGE[1])
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    hit = self.hud.hit(event.pos)
                    if hit:
                        self.handle_action(*hit, event.pos)
                    elif not self.hud.blocked(event.pos):
                        self.drag_start = pygame.Vector2(event.pos)
                elif event.button == 3:
                    self.drag_start = None
            elif event.type == pygame.MOUSEMOTION:
                if self.slider:
                    self.update_slider(event.pos)
                elif event.buttons[1]:          # middle-drag pans the view
                    if self.follow:
                        self.follow = False
                        self.clear_trails()
                    self.view.center -= pygame.Vector2(event.rel) / self.view.zoom
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.slider:
                    self.slider = None
                elif self.drag_start is not None:
                    self.throw(event.pos)

    # --- Simulation --------------------------------------------------------------------
    def update(self, frame_time):
        if not self.paused:
            self.accumulator += frame_time
            steps = int(self.accumulator / PHYSICS_DT)
            self.accumulator -= steps * PHYSICS_DT
            simulate(self.bodies, PHYSICS_DT, steps, self.mode)
            self.sim_time += steps * PHYSICS_DT

        if self.sun not in self.bodies and self.bodies:   # sun swallowed or flung away
            self.set_sun(max(self.bodies, key=lambda b: b.mass))
        if self.following:
            self.view.center = pygame.Vector2(self.sun.pos)

        # Delete bodies far outside the view (farther when zoomed out)
        cull = max(CULL_DISTANCE, 2 * math.hypot(WIDTH, HEIGHT) / self.view.zoom)
        self.bodies = [b for b in self.bodies if b.fixed or b is self.sun
                       or b.pos.distance_to(self.view.center) < cull]

        if self.show_trails and not self.paused:
            sun, following = self.sun, self.following
            for b in self.bodies:
                # While following, other trails are stored relative to the sun (so
                # orbits draw as clean loops); the sun's own trail stays in world
                # coordinates to show its path through space.
                if following and b is not sun:
                    b.trail.append((b.pos.x - sun.pos.x, b.pos.y - sun.pos.y))
                else:
                    b.trail.append((b.pos.x, b.pos.y))

    # --- Drawing ---------------------------------------------------------------------
    def draw(self):
        screen, view, sun, hud = self.screen, self.view, self.sun, self.hud
        mouse = pygame.Vector2(pygame.mouse.get_pos())
        following = self.following

        screen.blit(self.background, (0, 0))
        if self.show_trails:
            for b in self.bodies:
                rel = following and b is not sun
                b.draw_trail(screen, view, (sun.pos.x, sun.pos.y) if rel else (0.0, 0.0))
        for b in self.bodies:
            b.draw(screen, view)

        name, m, r, color = self.selected()
        aim = None
        if self.drag_start is not None:
            vel = self.launch_velocity(mouse)
            start = view.to_world(self.drag_start)
            v_circ = orbit = None
            if sun in self.bodies:
                v_circ = circular_speed(sun.mass, start.distance_to(sun.pos))
                rel_vel = vel if following else vel - sun.vel
                orbit = orbit_info(start - sun.pos, rel_vel, sun.mass, sun.radius + r)
            status_color = hud.orbit_status(orbit)[1]
            if self.show_preview:
                dot = [int(c * 0.6) for c in status_color]
                v0 = vel + sun.vel if following else vel
                for p in predict_path(self.bodies, tuple(start), tuple(v0),
                                      sun if following else None, r):
                    q = view.to_screen((p[0], p[1]))
                    pygame.draw.circle(screen, dot, (round(q.x), round(q.y)), 1)
            Body(start, m, r, color).draw(screen, view)
            draw_arrow(screen, self.drag_start,
                       self.drag_start + vel * (view.zoom / LAUNCH_SCALE), status_color)
            aim = (mouse, vel.length(), v_circ, orbit)
        elif not hud.blocked(mouse):
            pygame.draw.circle(screen, color, mouse, max(1, round(r * view.zoom)), 1)

        # --- UI ---
        hud.begin(mouse, self.slider[0] if self.slider else None)
        toggles = [
            ("M", "Collisions", self.mode.upper(), True, ("key", pygame.K_m)),
            ("L", "Trails", "ON" if self.show_trails else "OFF", self.show_trails,
             ("key", pygame.K_l)),
            ("T", "Aim preview", "ON" if self.show_preview else "OFF", self.show_preview,
             ("key", pygame.K_t)),
            ("V", "Camera", "FOLLOW SUN" if following else "FIXED", following,
             ("key", pygame.K_v)),
            ("0", "Zoom", f"{view.zoom:.2f}x", abs(view.zoom - 1) > 1e-6, ("key", pygame.K_0)),
        ]
        status = hud.draw_status(screen, self.clock.get_fps(), len(self.bodies),
                                 self.sim_time, toggles)
        ti = self.sun_type_index()
        (mlo, mhi), (rlo, rhi) = SUN_MASS_RANGE, SUN_RADIUS_RANGE
        hud.draw_sun_panel(
            screen, status.bottom + 10, SUN_TYPES, ti,
            SUN_TYPES[ti][0] if ti is not None else "Custom",
            sun.mass, sun.radius,
            math.log(max(sun.mass, 1) / mlo) / math.log(mhi / mlo),
            (sun.radius - rlo) / (rhi - rlo),
            sun.fixed, sun.accent)
        hud.draw_controls(screen)
        hud.draw_toolbar(screen, PRESETS, self.preset_idx, r, m, self.size_mult,
                         self.mass_mult, SIZE_RANGE, MASS_RANGE)
        if self.paused:
            hud.draw_paused(screen)
        if aim:                                   # on top of everything else
            hud.draw_aim(screen, *aim)
        pygame.display.flip()

    def run(self):
        while self.running:
            frame_time = min(self.clock.tick(FPS) / 1000, MAX_FRAME_TIME)
            self.handle_events()
            self.update(frame_time)
            self.draw()
        pygame.quit()


def main():
    App().run()


if __name__ == "__main__":
    main()
