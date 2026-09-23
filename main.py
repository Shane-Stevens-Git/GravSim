"""GravSim - a 2D interactive gravity sandbox.

Step 4: full n-body gravity. Every body pulls on every other body
(including the sun, which is now free to move unless pinned with F).
The physics runs on NumPy arrays so dozens of bodies stay fast.
"""
import random

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
CULL_DISTANCE = 4000        # px from screen center; farther bodies are deleted

# --- Launch controls -----------------------------------------------------------
LAUNCH_SCALE = 1.0          # launch speed (px/s) per pixel dragged
SLINGSHOT = False           # False: drag the way it should go. True: pull back like a slingshot.
PREVIEW_STEPS = 320         # trajectory preview length (steps of PREVIEW_DT)
PREVIEW_DT = 1 / 40
PREVIEW_MAX_BODIES = 12     # preview only simulates the heaviest bodies (for speed)

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
        self.mass = mass
        self.radius = radius
        self.color = color
        self.fixed = fixed  # fixed ("pinned") bodies pull on others but never move

    @classmethod
    def glow_surface(cls, radius, color):
        """Soft translucent halo, cached per (radius, color)."""
        key = (radius, color)
        if key not in cls._glow_cache:
            size = radius * 6
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            c = radius * 3
            for i, alpha in enumerate((18, 30, 45)):
                pygame.draw.circle(surf, (*color, alpha), (c, c), int(radius * (2.6 - i * 0.5)))
            cls._glow_cache[key] = surf
        return cls._glow_cache[key]

    def draw(self, surface):
        center = (round(self.pos.x), round(self.pos.y))
        glow = self.glow_surface(self.radius, self.color)
        surface.blit(glow, (center[0] - self.radius * 3, center[1] - self.radius * 3))
        pygame.draw.circle(surface, self.color, center, self.radius)


# --- Physics -----------------------------------------------------------------
def accelerations(pos, mass):
    """N-body gravity: a_i = sum_j G*m_j * (p_j - p_i) / |p_j - p_i|^3.

    pos: (n, 2) array, mass: (n,) array. Computed for all pairs at once.
    """
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


def simulate(bodies, dt, steps):
    """Advance all bodies `steps` fixed steps and write results back."""
    if not bodies or steps == 0:
        return
    pos, vel, mass, movable = pack(bodies)
    acc = accelerations(pos, mass)
    for _ in range(steps):
        acc = verlet(pos, vel, acc, mass, movable, dt)
    for b, p, v in zip(bodies, pos, vel):
        b.pos.update(p[0], p[1])
        b.vel.update(v[0], v[1])


def predict_path(bodies, start, vel0):
    """Preview a throw: a massless test particle flown through the full
    n-body system (other bodies move during the preview too).

    Only the heaviest few bodies are included - tiny ones barely affect
    the path, and simulating everything every frame would be too slow.
    """
    bodies = sorted(bodies, key=lambda b: b.mass, reverse=True)[:PREVIEW_MAX_BODIES]
    pos, vel, mass, movable = pack(bodies)
    radii = np.array([b.radius for b in bodies], dtype=float)
    pos = np.vstack([pos, start])
    vel = np.vstack([vel, vel0])
    mass = np.append(mass, 0.0)                     # test particle pulls on nothing
    movable = np.vstack([movable, [[1.0]]])
    acc = accelerations(pos, mass)
    points = []
    for i in range(PREVIEW_STEPS):
        acc = verlet(pos, vel, acc, mass, movable, PREVIEW_DT)
        p = pos[-1]
        if len(radii) and (np.hypot(*(pos[:-1] - p).T) < radii).any():
            break                                   # would hit something
        if i % 3 == 0:
            points.append((round(p[0]), round(p[1])))
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
    """Sun plus the demo planet from step 2."""
    sun = Body((WIDTH / 2, HEIGHT / 2), mass=10_000, radius=30,
               color=(255, 200, 60), fixed=sun_fixed)
    r0 = 220
    v0 = 0.85 * circular_speed(sun.mass, r0)
    planet = Body((sun.pos.x + r0, sun.pos.y), mass=20, radius=8,
                  color=(90, 170, 255), vel=(0, -v0))
    # Give the sun the opposite momentum so the system's center of mass
    # stays put instead of slowly drifting off-screen.
    if not sun.fixed:
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
    sun = bodies[0]
    preset_idx = 2              # start on "Planet"
    drag_start = None           # mouse-down position while aiming, else None
    show_preview = True
    paused = False
    accumulator = 0.0

    def launch_velocity(mouse):
        v = (pygame.Vector2(mouse) - drag_start) * LAUNCH_SCALE
        return -v if SLINGSHOT else v

    running = True
    while running:
        frame_time = min(clock.tick(FPS) / 1000, MAX_FRAME_TIME)
        mouse = pygame.Vector2(pygame.mouse.get_pos())

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
                elif event.key == pygame.K_f and sun in bodies:   # pin / unpin the sun
                    sun.fixed = not sun.fixed
                    sun.vel.update(0, 0)
                elif event.key == pygame.K_c:     # clear everything but the sun
                    bodies = [b for b in bodies if b is sun]
                elif event.key == pygame.K_r:     # reset to the starting scene
                    bodies = make_scene(sun.fixed)
                    sun = bodies[0]
                elif pygame.K_1 <= event.key < pygame.K_1 + len(PRESETS):
                    preset_idx = event.key - pygame.K_1
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    drag_start = pygame.Vector2(event.pos)
                elif event.button == 3:           # right-click cancels a throw
                    drag_start = None
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and drag_start:
                _, mass, radius, color = PRESETS[preset_idx]
                bodies.append(Body(drag_start, mass, radius, color,
                                   vel=launch_velocity(event.pos)))
                drag_start = None

        # Fixed-timestep physics
        if not paused:
            accumulator += frame_time
            steps = int(accumulator / PHYSICS_DT)
            accumulator -= steps * PHYSICS_DT
            simulate(bodies, PHYSICS_DT, steps)

        # Remove bodies that have been flung far away
        center = pygame.Vector2(WIDTH / 2, HEIGHT / 2)
        bodies = [b for b in bodies if b.fixed or b.pos.distance_to(center) < CULL_DISTANCE]

        # --- Draw ---
        screen.blit(background, (0, 0))
        for body in bodies:
            body.draw(screen)

        name, mass, radius, color = PRESETS[preset_idx]
        aim_text = ""
        if drag_start is not None:
            vel = launch_velocity(mouse)
            if show_preview:
                for p in predict_path(bodies, (drag_start.x, drag_start.y), (vel.x, vel.y)):
                    pygame.draw.circle(screen, (120, 120, 150), p, 1)
            Body(drag_start, mass, radius, color).draw(screen)
            draw_arrow(screen, drag_start, drag_start + vel / LAUNCH_SCALE, (230, 230, 240))
            if sun in bodies:
                v_circ = circular_speed(sun.mass, drag_start.distance_to(sun.pos))
                aim_text = f"   launch {vel.length():6.1f} px/s  (circular here: {v_circ:5.1f})"
        else:
            pygame.draw.circle(screen, color, mouse, radius, 1)

        lines = [
            f"FPS {clock.get_fps():5.1f}   bodies {len(bodies)}   "
            f"sun {'PINNED' if sun.fixed else 'free'}{'   PAUSED' if paused else ''}",
            f"[1-5] type: {name} (mass {mass}, r {radius}){aim_text}",
            "drag to throw  [RMB] cancel  [T] preview  [F] pin sun  [C] clear  "
            "[R] reset  [Space] pause  [Esc] quit",
        ]
        for i, text in enumerate(lines):
            screen.blit(font.render(text, True, HUD_COLOR), (10, 10 + i * 20))
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
