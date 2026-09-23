"""Bodies and the camera view (what things are and how they're drawn)."""
from collections import deque

import pygame

from config import *


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

    def __init__(self, pos, mass, radius, color, vel=(0, 0), fixed=False, kind="body",
                 name="Body", particle=False):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.mass = float(mass)
        self.radius = int(radius)
        self.color = tuple(int(c) for c in color)
        self.fixed = fixed  # fixed ("pinned") bodies pull on others but never move
        self.kind = kind    # "body", "star" or "blackhole" (affects drawing only)
        self.name = name    # shown in the inspector
        # A "test particle" (belt asteroid, galaxy star) feels gravity but exerts
        # none, and never collides with other particles - see physics.accelerations.
        self.particle = particle
        self.trail = deque(maxlen=PARTICLE_TRAIL_LENGTH if particle else TRAIL_LENGTH)

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
