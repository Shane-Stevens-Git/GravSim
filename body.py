"""Bodies and the camera view (what things are and how they're drawn)."""
from collections import deque

import numpy as np
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
                 name="Body", particle=False, soft=SOFTENING, absorbs=True):
        """kind: "body", "star", "blackhole" or "craft" (spacecraft)."""
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
        # Gravity softening length (px). Galaxy cores use a large one: their
        # mass is spread out, so their pull levels off close in.
        self.soft = soft
        # False: test particles pass through instead of being absorbed (galaxy
        # cores - real stars almost never hit the central black hole).
        self.absorbs = absorbs
        self.thrust = pygame.Vector2()     # engine acceleration (spacecraft only)
        self.heading = -90.0               # degrees; where a craft's nose points
        self.pilot = None                  # craft.Autopilot for spacecraft
        self.ring_color = BLACK_HOLE_RING  # black holes: color of the glowing ring
        self.trail = deque(maxlen=PARTICLE_TRAIL_LENGTH if particle else TRAIL_LENGTH)

    @property
    def accent(self):
        """Color for glow and trail - a black hole uses its glowing ring."""
        return self.ring_color if self.kind == "blackhole" else self.color

    @classmethod
    def glow_surface(cls, radius, color, star):
        """Bloom: a smooth radial falloff (brightness ~ 1 / (1 + (d/r)^2)),
        drawn with additive blending so overlapping glows brighten. Stars get
        a wider, stronger bloom. Cached per (radius, color, star)."""
        key = (radius, color, star)
        if key not in cls._glow_cache:
            if len(cls._glow_cache) > 300:
                cls._glow_cache.clear()
            extent = radius * (GLOW_STAR_EXTENT if star else GLOW_BODY_EXTENT)
            size = int(extent * 2) + 2
            y, x = np.ogrid[:size, :size]
            d = np.hypot(x - size / 2, y - size / 2)
            strength, spread = (0.6, 1.0) if star else (0.35, 2.5)
            intensity = (strength / (1 + (d / radius) ** 2 * spread)
                         * np.clip(1 - d / extent, 0, 1) ** 2)
            rgb = np.clip(np.array(color, dtype=float) * intensity[..., None], 0, 255)
            cls._glow_cache[key] = pygame.surfarray.make_surface(
                rgb.astype(np.uint8).transpose(1, 0, 2))
        return cls._glow_cache[key]

    def draw(self, surface, view):
        p = view.to_screen(self.pos)
        cx, cy = round(p.x), round(p.y)
        r = max(1, round(self.radius * view.zoom))
        if not (-r * 5 < cx < WIDTH + r * 5 and -r * 5 < cy < HEIGHT + r * 5):
            return
        if 2 <= r <= 90 and not self.particle:
            glow = self.glow_surface(r, self.accent, self.kind in ("star", "blackhole"))
            half = glow.get_width() // 2
            surface.blit(glow, (cx - half, cy - half), special_flags=pygame.BLEND_RGB_ADD)
        if self.kind == "craft":
            self.draw_craft(surface, cx, cy, view)
            return
        if self.kind == "blackhole":
            pygame.draw.circle(surface, self.ring_color, (cx, cy),
                               r + max(2, r // 4), max(1, r // 6))
            pygame.draw.circle(surface, (0, 0, 0), (cx, cy), r)
        else:
            pygame.draw.circle(surface, self.color, (cx, cy), r)

    def draw_craft(self, surface, cx, cy, view):
        """A little arrowhead pointing along `heading`, with an engine flame
        whose length shows how hard it's thrusting."""
        size = max(8, self.radius * view.zoom * 2.2)
        fwd = pygame.Vector2(1, 0).rotate(self.heading)
        side = fwd.rotate(90)
        c = pygame.Vector2(cx, cy)
        a = self.thrust.length()
        if a > 0.3:
            flame_len = size * (0.6 + min(a / 60, 2.2))
            tail = c - fwd * size * 0.6
            flicker = 1 + 0.15 * ((pygame.time.get_ticks() // 40) % 3 - 1)
            tip = tail - fwd * flame_len * flicker
            pygame.draw.polygon(surface, (255, 150, 60),
                                [tail + side * size * 0.35, tip, tail - side * size * 0.35])
            pygame.draw.polygon(surface, (255, 235, 170),
                                [tail + side * size * 0.18, tail - fwd * flame_len * 0.55,
                                 tail - side * size * 0.18])
        nose = c + fwd * size
        pts = [nose, c - fwd * size * 0.7 + side * size * 0.7, c - fwd * size * 0.35,
               c - fwd * size * 0.7 - side * size * 0.7]
        pygame.draw.polygon(surface, self.color, pts)
        pygame.draw.polygon(surface, (40, 50, 80), pts, 1)

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
