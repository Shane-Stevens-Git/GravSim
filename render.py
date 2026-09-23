"""Small drawing helpers."""
import random

import numpy as np

import pygame

from config import *


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


def draw_points(surface, bodies, view):
    """Draw many small bodies (galaxy stars, belt particles) at once as 2x2
    dots written straight into the screen's pixels - far faster than one
    draw call per body when there are thousands."""
    if not bodies:
        return
    pos = np.array([(b.pos.x, b.pos.y) for b in bodies], dtype=float)
    col = np.array([b.color for b in bodies], dtype=np.uint8)
    sx = ((pos[:, 0] - view.center.x) * view.zoom + view.screen_center.x).astype(int)
    sy = ((pos[:, 1] - view.center.y) * view.zoom + view.screen_center.y).astype(int)
    w, h = surface.get_size()
    ok = (sx >= 0) & (sx < w - 1) & (sy >= 0) & (sy < h - 1)
    sx, sy, col = sx[ok], sy[ok], col[ok]
    px = pygame.surfarray.pixels3d(surface)
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        px[sx + dx, sy + dy] = col
    del px      # release the pixel lock
