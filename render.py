"""Small drawing helpers."""
import random

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
