"""GravSim - a 2D interactive gravity sandbox.

Step 1: open a window and render a single static "sun".
"""
import random

import pygame

# --- Window / timing -------------------------------------------------------
WIDTH, HEIGHT = 1280, 800
FPS = 60
BG_COLOR = (8, 10, 20)


class Body:
    """A circular mass in the simulation.

    Position and velocity are stored as pygame Vector2 so the physics
    steps later on can use vector math directly.
    """

    def __init__(self, pos, mass, radius, color, vel=(0, 0), fixed=False):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.mass = mass
        self.radius = radius
        self.color = color
        self.fixed = fixed  # fixed bodies never move (e.g. the sun, for now)

    def draw(self, surface):
        center = (round(self.pos.x), round(self.pos.y))
        # Soft glow: a few translucent rings drawn behind the body.
        glow = pygame.Surface((self.radius * 6, self.radius * 6), pygame.SRCALPHA)
        gc = self.radius * 3
        for i, alpha in enumerate((18, 30, 45)):
            r = int(self.radius * (2.6 - i * 0.5))
            pygame.draw.circle(glow, (*self.color, alpha), (gc, gc), r)
        surface.blit(glow, (center[0] - gc, center[1] - gc))
        pygame.draw.circle(surface, self.color, center, self.radius)


def make_starfield(n=250):
    """Pre-render a static background of faint stars."""
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

    sun = Body(
        pos=(WIDTH / 2, HEIGHT / 2),
        mass=10_000,
        radius=30,
        color=(255, 200, 60),
        fixed=True,
    )
    bodies = [sun]

    running = True
    while running:
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        screen.blit(background, (0, 0))
        for body in bodies:
            body.draw(screen)

        hud = font.render(
            f"FPS {clock.get_fps():5.1f}   bodies {len(bodies)}   [Esc] quit",
            True, (170, 170, 190),
        )
        screen.blit(hud, (10, 10))
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
