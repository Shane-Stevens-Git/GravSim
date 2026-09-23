"""Gravity field overlay: gravitational potential drawn as a heatmap with
soft contour lines, so you can see the 'wells' around each mass and how
they merge.

The potential depth G*M/r is summed over all regular bodies (test particles
exert no gravity) on a coarse grid, colored on one hue from transparent
(shallow) to bright (deep), with a contour every quarter decade, then
smooth-scaled up to the screen.
"""
import numpy as np
import pygame

from config import *

SHALLOW = np.array([30, 40, 110], dtype=float)    # one hue, dark -> bright
DEEP = np.array([150, 170, 255], dtype=float)
CONTOUR = np.array([200, 210, 255], dtype=float)


class FieldOverlay:
    def __init__(self):
        self.size = None
        self.image = None
        self.frame = 0

    def _build(self, size):
        """(Re)build the sample grid for a window size."""
        self.size = size
        self.gw, self.gh = max(1, size[0] // FIELD_CELL), max(1, size[1] // FIELD_CELL)
        self.small = pygame.Surface((self.gw, self.gh), pygame.SRCALPHA)
        ix = (np.arange(self.gw) + 0.5) * FIELD_CELL - size[0] / 2
        iy = (np.arange(self.gh) + 0.5) * FIELD_CELL - size[1] / 2
        self.sx, self.sy = np.meshgrid(ix, iy, indexing="ij")   # (x, y) like surfarray
        self.image = None

    def draw(self, surface, bodies, view):
        if surface.get_size() != self.size:
            self._build(surface.get_size())
        # The field changes smoothly, so recompute every other frame.
        if self.image is None or self.frame % 2 == 0:
            self.image = self._render(bodies, view)
        self.frame += 1
        surface.blit(self.image, (0, 0))

    def _render(self, bodies, view):
        wx = self.sx / view.zoom + view.center.x
        wy = self.sy / view.zoom + view.center.y
        depth = np.zeros_like(wx)
        for b in bodies:
            if b.particle:
                continue
            # Use the body's own radius as the core so the inside of a star is flat
            r2 = (wx - b.pos.x) ** 2 + (wy - b.pos.y) ** 2 + b.radius ** 2
            depth += G * b.mass / np.sqrt(r2)
        logd = np.log10(np.maximum(depth, 1e-9))
        # Map: FIELD_LOG_RANGE decades below FIELD_LOG_TOP fades to transparent.
        t = np.clip((logd - (FIELD_LOG_TOP - FIELD_LOG_RANGE)) / FIELD_LOG_RANGE, 0, 1)
        rgb = SHALLOW + (DEEP - SHALLOW) * t[..., None]
        alpha = 115 * t ** 2
        # Contour lines, 4 per decade of depth. A smooth bump (not a hard mask)
        # around each contour value, so the upscaled lines come out anti-aliased.
        band = (logd * 4) % 1.0
        dist = np.minimum(band, 1.0 - band)                 # 0 on a contour line
        line = np.exp(-(dist / 0.045) ** 2) * np.clip(t * 4, 0, 1)
        rgb += (CONTOUR - rgb) * line[..., None]
        alpha = np.maximum(alpha, 75 * line)
        pygame.surfarray.pixels3d(self.small)[:] = rgb.astype(np.uint8)
        pygame.surfarray.pixels_alpha(self.small)[:] = alpha.astype(np.uint8)
        return pygame.transform.smoothscale(self.small, self.size)
