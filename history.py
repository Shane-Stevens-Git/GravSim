"""Rewind: a rolling buffer of snapshots of the whole simulation.

Snapshots keep references to the Body objects themselves plus copies of
their state, so rewinding restores bodies that have since merged away or
been deleted, and the camera target / selection keep pointing at the same
objects. Spacecraft autopilots (mode, target, transfer phase, tour, delta-v)
and the debris random-number state are captured too, so a rewound run
continues exactly as it originally did.
"""
import copy
from collections import deque

from config import REWIND_INTERVAL, REWIND_SECONDS


def _pilot_state(pilot):
    """A detached copy of an autopilot's fields (lists/vectors copied)."""
    return _detach(pilot.__dict__)


def _detach(fields):
    return {**fields, "itinerary": list(fields["itinerary"]),
            "burn_left": copy.copy(fields["burn_left"])}


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

    def record(self, sim_time, bodies, sun, target, rng=None):
        """Store a snapshot every REWIND_INTERVAL of simulated time."""
        if sim_time < self.next_time:
            return
        self.next_time = sim_time + REWIND_INTERVAL
        self.snaps.append((sim_time, sun, target, rng.getstate() if rng else None, [
            (b, b.pos.x, b.pos.y, b.vel.x, b.vel.y, b.mass, b.radius, b.color,
             b.fixed, b.kind, b.particle, b.soft, b.heading,
             _pilot_state(b.pilot) if b.pilot else None)
            for b in bodies]))

    def rewind(self, rng=None):
        """Pop the newest snapshot and restore it (and `rng`'s state).
        Returns (sim_time, bodies, sun, target) or None when empty."""
        if not self.snaps:
            return None
        sim_time, sun, target, rng_state, state = self.snaps.pop()
        bodies = []
        for (b, px, py, vx, vy, mass, radius, color, fixed, kind, particle, soft,
             heading, pilot) in state:
            b.pos.update(px, py)
            b.vel.update(vx, vy)
            b.mass, b.radius, b.color = mass, radius, color
            b.fixed, b.kind, b.particle, b.soft = fixed, kind, particle, soft
            b.heading = heading
            if pilot is not None and b.pilot is not None:
                # copy again, so rewinding to the same snapshot twice works
                b.pilot.__dict__.update(_detach(pilot))
            bodies.append(b)
        if rng is not None and rng_state is not None:
            rng.setstate(rng_state)
        self.next_time = sim_time          # record again from here on
        return sim_time, bodies, sun, target
