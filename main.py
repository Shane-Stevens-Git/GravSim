"""GravSim - a 2D interactive gravity sandbox.

Step 3: click-and-drag to launch new bodies. Pick a body type with the
number keys, press the mouse where it should start, drag to set its
velocity, release to throw. Bodies are still only pulled by the sun
(full n-body comes in step 4).
"""
import math
import random

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
PREVIEW_STEPS = 480         # trajectory preview length (steps of PREVIEW_DT)
PREVIEW_DT = 1 / 60

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
        self.acc = pygame.Vector2(0, 0)
        self.mass = mass
        self.radius = radius
        self.color = color
        self.fixed = fixed  # fixed bodies never move (the sun, for now)

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
def gravity_accel(pos, attractors, exclude=None):
    """Acceleration at `pos` from every attractor: a = G*M / r^2, toward M."""
    acc = pygame.Vector2(0, 0)
    for other in attractors:
        if other is exclude:
            continue
        d = other.pos - pos
        dist_sq = d.length_squared() + SOFTENING ** 2
        acc += d * (G * other.mass / (dist_sq * math.sqrt(dist_sq)))
    return acc


def physics_step(bodies, dt):
    """Advance one fixed step with velocity Verlet (keeps orbits stable).

    Step 3: only fixed bodies (the sun) pull on things.
    """
    movers = [b for b in bodies if not b.fixed]
    attractors = [b for b in bodies if b.fixed]

    for b in movers:                       # 1. drift positions
        b.pos += b.vel * dt + 0.5 * b.acc * dt * dt
    for b in movers:                       # 2. new accel, 3. kick velocity
        new_acc = gravity_accel(b.pos, attractors, exclude=b)
        b.vel += 0.5 * (b.acc + new_acc) * dt
        b.acc = new_acc


def predict_path(pos, vel, attractors):
    """Integrate a test particle forward to preview where a throw will go."""
    pos, vel = pygame.Vector2(pos), pygame.Vector2(vel)
    acc = gravity_accel(pos, attractors)
    points = []
    for i in range(PREVIEW_STEPS):
        pos += vel * PREVIEW_DT + 0.5 * acc * PREVIEW_DT ** 2
        new_acc = gravity_accel(pos, attractors)
        vel += 0.5 * (acc + new_acc) * PREVIEW_DT
        acc = new_acc
        if any(pos.distance_to(a.pos) < a.radius for a in attractors):
            break  # would hit something
        if i % 4 == 0:
            points.append((round(pos.x), round(pos.y)))
    return points


def circular_speed(central_mass, r):
    """Speed needed for a circular orbit of radius r: v = sqrt(G*M/r)."""
    return math.sqrt(G * central_mass / max(r, 1e-6))


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
    left, right = d.rotate(150), d.rotate(-150)
    pygame.draw.polygon(surface, color, [end, end + left, end + right])


def make_scene():
    """Sun plus the demo planet from step 2."""
    sun = Body((WIDTH / 2, HEIGHT / 2), mass=10_000, radius=30,
               color=(255, 200, 60), fixed=True)
    r0 = 220
    v0 = 0.85 * circular_speed(sun.mass, r0)
    planet = Body((sun.pos.x + r0, sun.pos.y), mass=20, radius=8,
                  color=(90, 170, 255), vel=(0, -v0))
    bodies = [sun, planet]
    for b in bodies:
        b.acc = gravity_accel(b.pos, [o for o in bodies if o.fixed], exclude=b)
    return bodies


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("GravSim")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 16)
    background = make_starfield()

    bodies = make_scene()
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
                elif event.key == pygame.K_c:     # clear everything but fixed bodies
                    bodies = [b for b in bodies if b.fixed]
                elif event.key == pygame.K_r:     # reset to the starting scene
                    bodies = make_scene()
                elif pygame.K_1 <= event.key < pygame.K_1 + len(PRESETS):
                    preset_idx = event.key - pygame.K_1
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    drag_start = pygame.Vector2(event.pos)
                elif event.button == 3:           # right-click cancels a throw
                    drag_start = None
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and drag_start:
                _, mass, radius, color = PRESETS[preset_idx]
                body = Body(drag_start, mass, radius, color, vel=launch_velocity(event.pos))
                body.acc = gravity_accel(body.pos, [b for b in bodies if b.fixed])
                bodies.append(body)
                drag_start = None

        # Fixed-timestep physics
        if not paused:
            accumulator += frame_time
            while accumulator >= PHYSICS_DT:
                physics_step(bodies, PHYSICS_DT)
                accumulator -= PHYSICS_DT

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
            attractors = [b for b in bodies if b.fixed]
            if show_preview:
                for p in predict_path(drag_start, vel, attractors):
                    pygame.draw.circle(screen, (120, 120, 150), p, 1)
            ghost = Body(drag_start, mass, radius, color)
            ghost.draw(screen)
            arrow_end = drag_start + vel / LAUNCH_SCALE
            draw_arrow(screen, drag_start, arrow_end, (230, 230, 240))
            # Reference: speed for a circular orbit around the sun at this spot
            sun = attractors[0]
            v_circ = circular_speed(sun.mass, drag_start.distance_to(sun.pos))
            aim_text = f"   launch {vel.length():6.1f} px/s  (circular here: {v_circ:5.1f})"
        else:
            # Hover preview of the selected body under the cursor
            pygame.draw.circle(screen, color, mouse, radius, 1)

        lines = [
            f"FPS {clock.get_fps():5.1f}   bodies {len(bodies)}"
            f"{'   PAUSED' if paused else ''}",
            f"[1-5] type: {name} (mass {mass}, r {radius}){aim_text}",
            "drag to throw  [RMB] cancel  [T] preview  [C] clear  [R] reset  "
            "[Space] pause  [Esc] quit",
        ]
        for i, text in enumerate(lines):
            screen.blit(font.render(text, True, HUD_COLOR), (10, 10 + i * 20))
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
