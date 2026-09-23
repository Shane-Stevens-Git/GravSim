"""Visual effects: parallax starfield and collision flashes."""
import math

import numpy as np
import pygame

from config import *


class Starfield:
    """Three layers of background stars that drift at different rates as the
    camera moves (far stars barely move, near ones more), so camera motion -
    like following a drifting sun - is visible. Drawn straight into pixels."""

    LAYERS = ((0.02, 260, 60, 130), (0.06, 120, 110, 190), (0.14, 45, 170, 255))

    def __init__(self, seed=42):
        rng = np.random.default_rng(seed)
        self.layers = []
        for factor, n, lo, hi in self.LAYERS:
            xy = rng.uniform(0, 1, (n, 2)) * (WIDTH, HEIGHT)
            bright = rng.uniform(lo, hi, n)
            tint = rng.choice([0, 1, 2], n, p=[0.7, 0.15, 0.15])   # white / blue / warm
            col = np.stack([bright, bright, bright], axis=1)
            col[tint == 1] *= (0.8, 0.9, 1.0)
            col[tint == 2] *= (1.0, 0.9, 0.75)
            self.layers.append((factor, xy, col.astype(np.uint8), rng.uniform(0, 6.28, n)))

    def draw(self, surface, view):
        surface.fill(BG_COLOR)
        px = pygame.surfarray.pixels3d(surface)
        t = pygame.time.get_ticks() / 1000
        for k, (factor, xy, col, phase) in enumerate(self.layers):
            sx = ((xy[:, 0] - view.center.x * factor) % WIDTH).astype(int)
            sy = ((xy[:, 1] - view.center.y * factor) % HEIGHT).astype(int)
            c = col
            if k == 2:                            # near stars twinkle a little
                c = (col * (0.85 + 0.15 * np.sin(t * 2 + phase))[:, None]).astype(np.uint8)
            px[sx, sy] = c
            if k == 2:                            # and are 2 px wide
                px[np.minimum(sx + 1, WIDTH - 1), sy] = c // 2
        del px


class Flashes:
    """Expanding, fading rings + glow where collisions happen."""

    COLORS = {"merge": (255, 220, 160), "shatter": (255, 150, 90),
              "bounce": (170, 200, 255), "tidal": (255, 120, 200)}

    def __init__(self):
        self.items = []          # (world pos, start ms, size, color)

    def add(self, kind, pos, strength):
        size = min(max(6 + 4 * math.log10(max(strength, 1.0)), 8), 60)
        self.items.append((pygame.Vector2(pos), pygame.time.get_ticks(), size,
                           self.COLORS.get(kind, (255, 255, 255))))
        del self.items[:-40]     # cap

    def draw(self, surface, view):
        now = pygame.time.get_ticks()
        alive = []
        for pos, start, size, color in self.items:
            age = (now - start) / FLASH_MS
            if age >= 1:
                continue
            alive.append((pos, start, size, color))
            p = view.to_screen(pos)
            r = max(2, round(size * view.zoom ** 0.5 * (0.4 + 1.6 * age)))
            fade = (1 - age) ** 2
            glow = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*color, int(90 * fade)), (r + 1, r + 1), r)
            pygame.draw.circle(glow, (*color, int(230 * fade)), (r + 1, r + 1), r, max(1, r // 6))
            surface.blit(glow, (p.x - r - 1, p.y - r - 1))
        self.items = alive
