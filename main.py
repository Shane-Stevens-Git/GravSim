"""GravSim - a 2D interactive gravity sandbox.

Step 2: one moving body pulled toward a fixed sun by real
inverse-square gravity (no scripted orbit - just F = G*m1*m2/r^2).
"""
import math
import random

import pygame

# --- Window / timing -------------------------------------------------------
WIDTH, HEIGHT = 1280, 800
FPS = 60
BG_COLOR = (8, 10, 20)

# --- Physics -----------------------------------------------------------------
# Units: distance in pixels, time in seconds, mass in arbitrary "mass units".
# G is tuned so orbits a few hundred pixels out take several seconds.
G = 500.0
PHYSICS_DT = 1 / 240        # fixed physics step (s), independent of frame rate
MAX_FRAME_TIME = 0.05       # don't try to "catch up" more than this after a stall
SOFTENING = 5.0             # px; avoids infinite force if r -> 0


class Body:
    """A circular mass in the simulation."""

    def __init__(self, pos, mass, radius, color, vel=(0, 0), fixed=False):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.acc = pygame.Vector2(0, 0)
        self.mass = mass
        self.radius = radius
        self.color = color
        self.fixed = fixed  # fixed bodies never move (the sun, for now)

    def draw(self, surface):
        center = (round(self.pos.x), round(self.pos.y))
        glow = pygame.Surface((self.radius * 6, self.radius * 6), pygame.SRCALPHA)
        gc = self.radius * 3
        for i, alpha in enumerate((18, 30, 45)):
            r = int(self.radius * (2.6 - i * 0.5))
            pygame.draw.circle(glow, (*self.color, alpha), (gc, gc), r)
        surface.blit(glow, (center[0] - gc, center[1] - gc))
        pygame.draw.circle(surface, self.color, center, self.radius)


# --- Physics -----------------------------------------------------------------
def gravity_accel(body, attractors):
    """Acceleration on `body` from every attractor: a = G*M / r^2, toward M."""
    acc = pygame.Vector2(0, 0)
    for other in attractors:
        if other is body:
            continue
        d = other.pos - body.pos
        dist_sq = d.length_squared() + SOFTENING ** 2
        # G*M/r^2 in the direction of d  ==  G*M * d / r^3
        acc += d * (G * other.mass / (dist_sq * math.sqrt(dist_sq)))
    return acc


def physics_step(bodies, dt):
    """Advance one fixed step with velocity Verlet.

    Verlet is 'symplectic': it keeps orbital energy from drifting over
    time, so orbits stay closed instead of slowly spiralling in or out
    (which is what plain Euler integration does).

    Step 2: only fixed bodies (the sun) pull on things.
    """
    movers = [b for b in bodies if not b.fixed]
    attractors = [b for b in bodies if b.fixed]

    for b in movers:                       # 1. drift positions
        b.pos += b.vel * dt + 0.5 * b.acc * dt * dt
    for b in movers:                       # 2. new accel, 3. kick velocity
        new_acc = gravity_accel(b, attractors)
        b.vel += 0.5 * (b.acc + new_acc) * dt
        b.acc = new_acc


def circular_speed(central_mass, r):
    """Speed needed for a circular orbit of radius r: v = sqrt(G*M/r)."""
    return math.sqrt(G * central_mass / r)


# --- Rendering helpers --------------------------------------------------------
def make_starfield(n=250):
    bg = pygame.Surface((WIDTH, HEIGHT))
    bg.fill(BG_COLOR)
    rng = random.Random(42)
    for _ in range(n):
        b = rng.randint(60, 180)
        bg.set_at((rng.randrange(WIDTH), rng.randrange(HEIGHT)), (b, b, b))
    return bg


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("GravSim")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 16)
    background = make_starfield()

    sun = Body((WIDTH / 2, HEIGHT / 2), mass=10_000, radius=30,
               color=(255, 200, 60), fixed=True)

    # Planet starts 220 px to the right, moving straight "up" at 85% of
    # circular speed -> it should trace a clearly elliptical, closed orbit.
    r0 = 220
    v0 = 0.85 * circular_speed(sun.mass, r0)
    planet = Body((sun.pos.x + r0, sun.pos.y), mass=1, radius=8,
                  color=(90, 170, 255), vel=(0, -v0))

    bodies = [sun, planet]
    for b in bodies:
        b.acc = gravity_accel(b, [o for o in bodies if o.fixed])

    def orbital_energy():
        """Specific orbital energy v^2/2 - G*M/r. Should stay ~constant."""
        r = math.sqrt((planet.pos - sun.pos).length_squared() + SOFTENING ** 2)
        return 0.5 * planet.vel.length_squared() - G * sun.mass / r

    e0 = orbital_energy()
    paused = False
    sim_time = 0.0
    accumulator = 0.0

    running = True
    while running:
        frame_time = min(clock.tick(FPS) / 1000, MAX_FRAME_TIME)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused

        # Fixed-timestep physics: run as many PHYSICS_DT steps as real time
        # has elapsed, so the orbit is the same at 30 fps or 144 fps.
        if not paused:
            accumulator += frame_time
            while accumulator >= PHYSICS_DT:
                physics_step(bodies, PHYSICS_DT)
                sim_time += PHYSICS_DT
                accumulator -= PHYSICS_DT

        screen.blit(background, (0, 0))
        for body in bodies:
            body.draw(screen)

        dist = planet.pos.distance_to(sun.pos)
        drift = (orbital_energy() - e0) / abs(e0) * 100
        lines = [
            f"FPS {clock.get_fps():5.1f}   bodies {len(bodies)}   "
            f"[Space] {'resume' if paused else 'pause'}   [Esc] quit",
            f"t {sim_time:7.1f}s   r {dist:6.1f}px   v {planet.vel.length():6.1f}px/s"
            f"   energy drift {drift:+.4f}%",
        ]
        for i, text in enumerate(lines):
            screen.blit(font.render(text, True, (170, 170, 190)), (10, 10 + i * 20))
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
