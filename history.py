"""Rewind: a rolling buffer of snapshots of the whole simulation.

Snapshots keep references to the Body objects themselves plus copies of
their state, so rewinding restores bodies that have since merged away or
been deleted, and the camera target / selection keep pointing at the same
objects.
"""
from collections import deque

from config import REWIND_INTERVAL, REWIND_SECONDS


class History:
    def __init__(self):
        self.snaps = deque(maxlen=int(REWIND_SECONDS / REWIND_INTERVAL))
        self.next_time = 0.0

    def clear(self, sim_time=0.0):
        self.snaps.clear()
        self.next_time = sim_time

    @property
    def seconds(self):
        """How far back we can currently rewind."""
        return len(self.snaps) * REWIND_INTERVAL

    def record(self, sim_time, bodies, sun, target):
        """Store a snapshot every REWIND_INTERVAL of simulated time."""
        if sim_time < self.next_time:
            return
        self.next_time = sim_time + REWIND_INTERVAL
        self.snaps.append((sim_time, sun, target, [
            (b, b.pos.x, b.pos.y, b.vel.x, b.vel.y, b.mass, b.radius, b.color,
             b.fixed, b.kind, b.particle, b.soft)
            for b in bodies]))

    def rewind(self):
        """Pop the newest snapshot and restore it. Returns (sim_time, bodies,
        sun, target) or None when the buffer is empty."""
        if not self.snaps:
            return None
        sim_time, sun, target, state = self.snaps.pop()
        bodies = []
        for (b, px, py, vx, vy, mass, radius, color, fixed, kind, particle, soft) in state:
            b.pos.update(px, py)
            b.vel.update(vx, vy)
            b.mass, b.radius, b.color = mass, radius, color
            b.fixed, b.kind, b.particle, b.soft = fixed, kind, particle, soft
            bodies.append(b)
        self.next_time = sim_time          # record again from here on
        return sim_time, bodies, sun, target
