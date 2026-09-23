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
            xy = rng.uniform(0, 1, (n, 2)) * (WIDTH, HEIGHT)    # one tile; repeated to fill
            bright = rng.uniform(lo, hi, n)
            tint = rng.choice([0, 1, 2], n, p=[0.7, 0.15, 0.15])   # white / blue / warm
            col = np.stack([bright, bright, bright], axis=1)
            col[tint == 1] *= (0.8, 0.9, 1.0)
            col[tint == 2] *= (1.0, 0.9, 0.75)
            self.layers.append((factor, xy, col.astype(np.uint8), rng.uniform(0, 6.28, n)))

    def draw(self, surface, view):
        surface.fill(BG_COLOR)
        w, h = surface.get_size()
        px = pygame.surfarray.pixels3d(surface)
        t = pygame.time.get_ticks() / 1000
        for k, (factor, xy, col, phase) in enumerate(self.layers):
            bx = (xy[:, 0] - view.center.x * factor) % WIDTH
            by = (xy[:, 1] - view.center.y * factor) % HEIGHT
            c = col
            if k == 2:                            # near stars twinkle a little
                c = (col * (0.85 + 0.15 * np.sin(t * 2 + phase))[:, None]).astype(np.uint8)
            # Repeat the star tile to cover windows bigger than it
            for ox in range(0, w, WIDTH):
                for oy in range(0, h, HEIGHT):
                    sx, sy = (bx + ox).astype(int), (by + oy).astype(int)
                    ok = (sx < w - 1) & (sy < h)
                    px[sx[ok], sy[ok]] = c[ok]
                    if k == 2:                    # near stars are 2 px wide
                        px[sx[ok] + 1, sy[ok]] = c[ok] // 2
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


class CometTails:
    """Comet tails, drawn every frame from where the comet is right now:
      * ion tail  - thin, blue-white, pointing straight away from the star
                    (gas pushed by the solar wind);
      * dust tail - wider, warmer, curving back along the comet's path
                    (dust lags behind the comet's motion).
    Both grow as the comet nears the star (sunlight ~ 1/r^2) and vanish far out."""

    def __init__(self):
        self.overlay = None

    def draw(self, surface, view, comets, stars):
        if not comets or not stars:
            return
        if self.overlay is None or self.overlay.get_size() != surface.get_size():
            self.overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        self.overlay.fill((0, 0, 0, 0))
        for c in comets:
            # the star lighting this comet most
            star = max(stars, key=lambda s: s.mass / max((s.pos - c.pos).length_squared(), 1.0))
            away = c.pos - star.pos
            d = away.length()
            if d < 1e-6:
                continue
            away /= d
            strength = min(COMET_TAIL_MAX, (COMET_TAIL_DIST / d) ** 2)
            length = COMET_TAIL_LEN * strength
            if length < 4:
                continue
            rel_v = c.vel - star.vel
            behind = -rel_v.normalize() if rel_v.length() > 1e-6 else away
            dust_dir = (away * 0.55 + behind * 0.45)
            dust_dir = dust_dir.normalize() if dust_dir.length() > 1e-6 else away
            self._tail(c, away, away, length * 1.2, (150, 200, 255), 0.35, view)
            self._tail(c, away, dust_dir, length, (255, 225, 170), 0.9, view)
        surface.blit(self.overlay, (0, 0))

    def _tail(self, comet, start_dir, end_dir, length, color, spread, view):
        """A fading tail from the comet, bending from start_dir to end_dir,
        drawn back-to-front as soft circles that widen and fade."""
        steps = 16
        z = view.zoom
        for i in range(steps, 0, -1):
            t = i / steps
            direction = (start_dir * (1 - t) + end_dir * t)
            if direction.length() > 1e-6:
                direction = direction.normalize()
            p = view.to_screen(comet.pos + direction * length * t)
            radius = max(1, round((comet.radius * 0.8 + length * spread * 0.12 * t) * z))
            alpha = int(150 * (1 - t) ** 1.6 + 12)
            pygame.draw.circle(self.overlay, (*color, min(alpha, 255)), (round(p.x), round(p.y)), radius)
