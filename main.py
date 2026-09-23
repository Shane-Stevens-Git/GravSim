"""GravSim - a 2D interactive gravity sandbox.

Real inverse-square n-body gravity. Pick a body type (1-5), fine-tune
its size/mass with the scroll wheel, then click-drag-release to throw it.
Bodies orbit, collide (merge or bounce), or get flung out of the scene.
"""
import random
from collections import deque

import numpy as np
import pygame

# --- Window / timing -------------------------------------------------------
WIDTH, HEIGHT = 1280, 800
FPS = 60
BG_COLOR = (8, 10, 20)
HUD_COLOR = (170, 170, 190)

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


class Body:
    """A circular mass in the simulation."""

    _glow_cache = {}

    def __init__(self, pos, mass, radius, color, vel=(0, 0), fixed=False):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.mass = float(mass)
        self.radius = int(radius)
        self.color = tuple(int(c) for c in color)
        self.fixed = fixed  # fixed ("pinned") bodies pull on others but never move
        self.trail = deque(maxlen=TRAIL_LENGTH)

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

    def draw(self, surface, cam):
        cx, cy = round(self.pos.x - cam.x), round(self.pos.y - cam.y)
        r = self.radius
        if -r * 3 < cx < WIDTH + r * 3 and -r * 3 < cy < HEIGHT + r * 3:
            surface.blit(self.glow_surface(r, self.color), (cx - r * 3, cy - r * 3))
            pygame.draw.circle(surface, self.color, (cx, cy), r)

    def draw_trail(self, surface, cam):
        """Fading line through recent positions (oldest = dimmest)."""
        pts = [(x - cam.x, y - cam.y) for x, y in self.trail]
        n = len(pts)
        if n < 2:
            return
        for band in range(TRAIL_BANDS):
            a = band * (n - 1) // TRAIL_BANDS
            b = (band + 1) * (n - 1) // TRAIL_BANDS + 1
            if b - a < 2:
                continue
            t = 0.65 * (band + 1) / TRAIL_BANDS
            col = [int(bg + (c - bg) * t) for bg, c in zip(BG_COLOR, self.color)]
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


def predict_path(bodies, start, vel0, frame_body=None):
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
        if (np.hypot(*(pos[:-1] - p).T) < radii).any():
            break                                   # would hit something
        if k is not None:
            p -= pos[k] - frame0
        if i % 3 == 0:
            points.append(p)
    return points


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


def make_scene(sun_fixed=False):
    """Sun plus a demo planet on an elliptical orbit."""
    sun = Body((WIDTH / 2, HEIGHT / 2), mass=10_000, radius=30,
               color=(255, 200, 60), fixed=sun_fixed)
    r0 = 220
    v0 = 0.85 * circular_speed(sun.mass, r0)
    planet = Body((sun.pos.x + r0, sun.pos.y), mass=20, radius=8,
                  color=(90, 170, 255), vel=(0, -v0))
    if not sun.fixed:   # zero total momentum so the system doesn't drift
        sun.vel = -planet.vel * planet.mass / sun.mass
    return [sun, planet]


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("GravSim")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 16)
    background = make_starfield()

    bodies = make_scene()
    sun = bodies[0]             # the "main" body: camera target, HUD reference
    sun.trail = deque(maxlen=SUN_TRAIL_LENGTH)
    preset_idx = 2              # start on "Planet"
    size_mult = mass_mult = 1.0
    drag_start = None           # screen position of mouse-down while aiming
    show_preview = True
    show_trails = True
    follow = True               # camera keeps the sun centered
    mode = "merge"              # collision mode: "merge" or "bounce"
    paused = False
    accumulator = 0.0
    cam = pygame.Vector2(0, 0)  # world position of the screen's top-left corner

    def launch_velocity(mouse):
        v = (pygame.Vector2(mouse) - drag_start) * LAUNCH_SCALE
        return -v if SLINGSHOT else v

    def selected():
        name, mass, radius, color = PRESETS[preset_idx]
        r = max(2, round(radius * size_mult))
        m = mass * size_mult ** 3 * mass_mult    # size keeps density; Shift changes it
        return name, m, r, color

    running = True
    while running:
        frame_time = min(clock.tick(FPS) / 1000, MAX_FRAME_TIME)
        mouse = pygame.Vector2(pygame.mouse.get_pos())
        following = follow and sun in bodies

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_t:
                    show_preview = not show_preview
                elif event.key == pygame.K_l:
                    show_trails = not show_trails
                    for b in bodies:
                        b.trail.clear()
                elif event.key == pygame.K_m:
                    mode = "bounce" if mode == "merge" else "merge"
                elif event.key == pygame.K_v:
                    follow = not follow
                    for b in bodies:              # old trails were in the old frame
                        b.trail.clear()
                elif event.key == pygame.K_f and sun in bodies:
                    sun.fixed = not sun.fixed
                    sun.vel.update(0, 0)
                elif event.key == pygame.K_c:
                    bodies = [b for b in bodies if b is sun]
                elif event.key == pygame.K_r:
                    bodies = make_scene(sun.fixed)
                    sun = bodies[0]
                    sun.trail = deque(maxlen=SUN_TRAIL_LENGTH)
                elif pygame.K_1 <= event.key < pygame.K_1 + len(PRESETS):
                    preset_idx = event.key - pygame.K_1
                    size_mult = mass_mult = 1.0
            elif event.type == pygame.MOUSEWHEEL:
                f = SCROLL_STEP ** event.y
                if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                    mass_mult = min(max(mass_mult * f, MASS_RANGE[0]), MASS_RANGE[1])
                else:
                    size_mult = min(max(size_mult * f, SIZE_RANGE[0]), SIZE_RANGE[1])
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    drag_start = pygame.Vector2(event.pos)
                elif event.button == 3:
                    drag_start = None
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and drag_start:
                _, m, r, color = selected()
                vel = launch_velocity(event.pos)
                if following:                     # throw relative to the sun's motion
                    vel += sun.vel
                bodies.append(Body(drag_start + cam, m, r, color, vel=vel))
                drag_start = None

        # --- Physics ---
        if not paused:
            accumulator += frame_time
            steps = int(accumulator / PHYSICS_DT)
            accumulator -= steps * PHYSICS_DT
            simulate(bodies, PHYSICS_DT, steps, mode)

        if sun not in bodies and bodies:          # sun got swallowed or flung away
            sun = max(bodies, key=lambda b: b.mass)
            sun.trail = deque(maxlen=SUN_TRAIL_LENGTH)   # its old trail was sun-relative
        following = follow and sun in bodies
        if following:
            cam = sun.pos - pygame.Vector2(WIDTH / 2, HEIGHT / 2)
        view_center = cam + pygame.Vector2(WIDTH / 2, HEIGHT / 2)
        bodies = [b for b in bodies
                  if b.fixed or b is sun or b.pos.distance_to(view_center) < CULL_DISTANCE]

        # --- Draw ---
        screen.blit(background, (0, 0))
        if show_trails:
            for b in bodies:
                if not paused:
                    # When following, other bodies' trails are stored relative to
                    # the sun (so orbits draw as clean loops), but the sun's own
                    # trail stays in world coordinates: it shows the sun's path
                    # through space, streaming out behind it on screen.
                    b.trail.append((b.pos.x, b.pos.y) if not following or b is sun
                                   else (b.pos.x - sun.pos.x, b.pos.y - sun.pos.y))
                if following and b is not sun:
                    b.draw_trail(screen, -sun.pos + cam)
                else:
                    b.draw_trail(screen, cam)
        for b in bodies:
            b.draw(screen, cam)

        name, m, r, color = selected()
        aim_text = ""
        if drag_start is not None:
            vel = launch_velocity(mouse)
            if show_preview:
                v0 = vel + sun.vel if following else vel
                for p in predict_path(bodies, tuple(drag_start + cam), tuple(v0),
                                      sun if following else None):
                    pygame.draw.circle(screen, (120, 120, 150),
                                       (round(p[0] - cam.x), round(p[1] - cam.y)), 1)
            Body(drag_start + cam, m, r, color).draw(screen, cam)
            draw_arrow(screen, drag_start, drag_start + vel / LAUNCH_SCALE, (230, 230, 240))
            if sun in bodies:
                v_circ = circular_speed(sun.mass, (drag_start + cam).distance_to(sun.pos))
                aim_text = f"   launch {vel.length():6.1f} px/s  (circular here: {v_circ:5.1f})"
        else:
            pygame.draw.circle(screen, color, mouse, r, 1)

        lines = [
            f"FPS {clock.get_fps():5.1f}   bodies {len(bodies)}   "
            f"collisions: {mode.upper()}   sun {'PINNED' if sun.fixed else 'free'}   "
            f"camera: {'follow sun' if following else 'fixed'}"
            f"{'   PAUSED' if paused else ''}",
            f"[1-5] {name}: mass {m:.4g}, radius {r}   "
            f"(scroll: size  Shift+scroll: mass){aim_text}",
            "drag to throw  [RMB] cancel  [M] merge/bounce  [L] trails  [T] preview  "
            "[V] camera  [F] pin sun",
            "[C] clear  [R] reset  [Space] pause  [Esc] quit",
        ]
        for i, text in enumerate(lines):
            screen.blit(font.render(text, True, HUD_COLOR), (10, 10 + i * 20))
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
