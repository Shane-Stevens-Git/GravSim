"""Spacecraft: bodies with an engine and an autopilot.

Every frame `steer()` picks an engine acceleration (craft.thrust), which the
physics adds on top of gravity. Fuel is unlimited, but the delta-v spent is
tracked - it shows how costly each manoeuvre is (hovering at unstable L1
costs far more than sitting at stable L4).

Autopilot modes
  off       engine off; the craft coasts like any other body
  hold      station-keeping: hold a Lagrange point, or a circular orbit
  transfer  Hohmann transfer to another body's orbit: wait for the launch
            window, burn, coast, then rendezvous (switches to follow)
  follow    rendezvous with a body and keep station just beside it
  manual    you fly it: Up = thrust, Down = brake, Left/Right = turn
"""
import math

import pygame

from config import *
from physics import corotating_velocity, dominant_body, hill_radius, lagrange_points

MODES = ("off", "hold", "transfer", "follow", "manual")


class Autopilot:
    def __init__(self):
        self.mode = "off"
        self.hold = None      # ("L", primary, secondary, label) or ("orbit", primary, radius)
        self.target = None    # body for transfer / follow
        self.phase = None     # transfer: "wait" -> "burn" -> "coast"
        self.prev_diff = None
        self.coast_until = 0.0
        self.status = "Autopilot off"
        self.dv = 0.0         # delta-v used so far (px/s)
        self.r2 = None        # transfer: target orbit radius at burn time
        self.burn_left = None # transfer: velocity change still to deliver
        self.coast_start_r = None

    def set_mode(self, mode, target=None, hold=None):
        if mode == "off":
            self.status = "Autopilot off - coasting"
        self.mode = mode
        self.target = target
        self.hold = hold
        self.phase = "wait" if mode == "transfer" else None
        self.prev_diff = None


def make_craft(body):
    """Turn a freshly created body into a spacecraft."""
    body.kind = "craft"
    body.pilot = Autopilot()
    body.absorbs = False      # dust and debris pass by; planets and stars still hit
    if body.vel.length() > 1e-6:
        body.heading = math.degrees(math.atan2(body.vel.y, body.vel.x))
    return body


def gravity_at(point, bodies, exclude=()):
    """Gravitational acceleration at `point` from the regular bodies."""
    acc = pygame.Vector2()
    for b in bodies:
        if b.particle or b in exclude:
            continue
        d = b.pos - point
        r2 = d.length_squared() + (b.soft ** 2 + SOFTENING ** 2) / 2
        acc += d * (G * b.mass / r2 ** 1.5)
    return acc


def _limit(v, amax):
    if v.length() > amax:
        v.scale_to_length(amax)
    return v


def _orbit_sign(pos, vel):
    """+1 / -1: which way something at (pos, vel) is going around the origin."""
    return 1 if pos.x * vel.y - pos.y * vel.x >= 0 else -1


def _wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def steer(craft, bodies, sim_dt, real_dt, keys):
    """Set craft.thrust for this frame. keys: set of held arrow names."""
    p = craft.pilot
    thrust = pygame.Vector2()
    try:
        thrust = {"off": _off, "hold": _hold, "transfer": _transfer,
                  "follow": _follow, "manual": _manual}[p.mode](craft, bodies, sim_dt, real_dt, keys)
    except _Lost as e:
        p.set_mode("off")
        p.status = str(e)                       # stays until another mode is picked
    craft.thrust = thrust
    if thrust.length() > 0.3 and p.mode != "manual":
        craft.heading = math.degrees(math.atan2(thrust.y, thrust.x))
    p.dv += thrust.length() * sim_dt


class _Lost(Exception):
    pass


def _need(body, bodies, what):
    if body is None or body not in bodies:
        raise _Lost(f"{what} is gone - autopilot off")


def _off(craft, bodies, sim_dt, real_dt, keys):
    return pygame.Vector2()


def _manual(craft, bodies, sim_dt, real_dt, keys):
    turn = ("right" in keys) - ("left" in keys)
    craft.heading += turn * MANUAL_TURN_RATE * real_dt
    push = ("up" in keys) - 0.6 * ("down" in keys)
    craft.pilot.status = "Manual: arrow keys fly (Up thrust, Down brake)"
    return pygame.Vector2(1, 0).rotate(craft.heading) * MANUAL_THRUST * push


def _hold(craft, bodies, sim_dt, real_dt, keys):
    p = craft.pilot
    if p.hold[0] == "L":
        _, prim, sec, label = p.hold
        _need(prim, bodies, prim.name if prim else "Primary")
        _need(sec, bodies, sec.name if sec else "Secondary")
        target = lagrange_points(prim, sec)[label]
        target_v = corotating_velocity(prim, sec, target)
        # The L-point is carried round in a circle; the acceleration that takes
        # is what gravity would supply if we were exactly on it.
        total = prim.mass + sec.mass
        bary = (prim.pos * prim.mass + sec.pos * sec.mass) / total
        sep, rel_v = sec.pos - prim.pos, sec.vel - prim.vel
        omega = (sep.x * rel_v.y - sep.y * rel_v.x) / sep.length_squared()
        target_a = -(target - bary) * omega * omega
        err = target - craft.pos
        a = (target_a - gravity_at(craft.pos, bodies, (craft,))
             + err * HOLD_KP + (target_v - craft.vel) * HOLD_KD)
        p.status = f"Holding {label} ({prim.name}-{sec.name}): {err.length():.1f} px off"
        return _limit(a, HOLD_MAX_THRUST)
    _, prim, radius = p.hold
    _need(prim, bodies, prim.name if prim else "Primary")
    rel = craft.pos - prim.pos
    r = max(rel.length(), 1e-6)
    rhat = rel / r
    rel_v = craft.vel - prim.vel
    s = _orbit_sign(rel, rel_v)
    tangent = rhat.rotate(90 * s)
    v_des = (prim.vel + tangent * math.sqrt(G * prim.mass / r)
             + rhat * (radius - r) * ORBIT_KR)
    # Feedforward: supply exactly the inward pull our *current* sideways
    # speed needs to curve round a circle, and cancel the rest of the
    # primary's pull. At orbital speed that's zero thrust; starting from rest
    # it hovers while the velocity term speeds us up (no falling in).
    v_side = rel_v.dot(tangent)
    pull = (gravity_at(craft.pos, bodies, (craft,))
            - gravity_at(prim.pos, bodies, (prim, craft)))       # relative to the primary
    feedforward = -rhat * (v_side * v_side / r) - pull
    p.status = f"Holding a {radius:.0f} px orbit of {prim.name} (now {r:.0f})"
    return _limit(feedforward + (v_des - craft.vel) * ORBIT_KD, HOLD_MAX_THRUST)


def _follow(craft, bodies, sim_dt, real_dt, keys):
    p = craft.pilot
    t = p.target
    _need(t, bodies, t.name if t else "Target")
    away = craft.pos - t.pos
    dist = away.length()
    direction = away / dist if dist > 1e-6 else pygame.Vector2(1, 0)
    standoff = t.radius + craft.radius + 8
    err = t.pos + direction * standoff - craft.pos
    v_des = t.vel + _limit(err * FOLLOW_KP, FOLLOW_MAX_SPEED)
    # Cancel the difference in gravity between us and the target, so we can
    # hover beside it instead of falling onto it.
    feedforward = gravity_at(t.pos, bodies, (t, craft)) - gravity_at(craft.pos, bodies, (craft,))
    a = feedforward + _limit((v_des - craft.vel) * FOLLOW_KD, FOLLOW_MAX_THRUST)
    rel_speed = (craft.vel - t.vel).length()
    if err.length() < 4 and rel_speed < 3:
        # Matched. Settle into an orbit around the target if it can hold one
        # (hovering beside it costs thrust every second); otherwise hover.
        orbit_r = t.pos.distance_to(craft.pos)
        host = dominant_body(t, bodies)
        if host is None or orbit_r < 0.45 * hill_radius(t, host):
            p.set_mode("hold", hold=("orbit", t, orbit_r))
            p.status = f"Rendezvous done - entering orbit around {t.name}"
            return a
        p.status = f"Matched with {t.name} - hovering beside it (too small to orbit here)"
    else:
        p.status = f"Rendezvous with {t.name}: {max(dist - standoff, 0):.0f} px, closing at {rel_speed:.0f} px/s"
    return a


def _transfer(craft, bodies, sim_dt, real_dt, keys):
    """Hohmann transfer: from a (roughly circular) orbit of radius r1 around P
    to the target's orbit r2. Burn when the target leads us by the phase
    angle that makes it arrive where we do, half a transfer orbit later."""
    p = craft.pilot
    t = p.target
    _need(t, bodies, t.name if t else "Target")
    prim = dominant_body(craft, bodies)
    if prim is None or prim is t or dominant_body(t, bodies) is not prim:
        p.set_mode("follow", target=t)            # not a same-sun transfer: fly direct
        return _follow(craft, bodies, sim_dt, real_dt, keys)
    mu = G * prim.mass
    rel = craft.pos - prim.pos
    r1, r2 = rel.length(), t.pos.distance_to(prim.pos)
    if abs(r2 - r1) < 25:
        p.set_mode("follow", target=t)            # already at its distance
        return _follow(craft, bodies, sim_dt, real_dt, keys)
    s = _orbit_sign(rel, craft.vel - prim.vel)
    t_transfer = math.pi * math.sqrt(((r1 + r2) / 2) ** 3 / mu)

    if p.phase == "wait":
        n2 = math.sqrt(mu / r2 ** 3) * _orbit_sign(t.pos - prim.pos, t.vel - prim.vel) * s
        needed = math.pi - n2 * t_transfer       # how far ahead the target must be
        tr = t.pos - prim.pos
        ahead = s * (math.atan2(tr.y, tr.x) - math.atan2(rel.y, rel.x))
        diff = _wrap(ahead - needed)
        if p.prev_diff is not None and abs(diff) < 0.5 and (diff == 0 or (diff > 0) != (p.prev_diff > 0)):
            # Ignition: work out the whole velocity change now (as mission
            # planners do) and deliver exactly that, instead of re-aiming
            # at a target that shifts as we climb.
            p.phase, p.r2 = "burn", r2
            tangent = (rel / r1).rotate(90 * s)
            v_needed = math.sqrt(mu * (2 / r1 - 2 / (r1 + r2)))
            p.burn_left = prim.vel + tangent * v_needed - craft.vel
            p.coast_start_r = r1
        else:
            p.prev_diff = diff
            p.status = (f"Transfer to {t.name}: waiting for launch window "
                        f"({math.degrees(abs(diff)):.0f} deg to go)")
            return pygame.Vector2()

    if p.phase == "burn":
        left = p.burn_left.length()
        if left < 0.05 or sim_dt <= 0:
            p.phase = "coast" if left < 0.05 else "burn"
        else:
            a = p.burn_left / left * min(TRANSFER_MAX_THRUST, left / sim_dt)
            p.burn_left -= a * sim_dt
            p.status = f"Transfer to {t.name}: burning ({left:.0f} px/s to go)"
            return a

    # coast along the transfer ellipse, then hand over to rendezvous
    outward = p.r2 > p.coast_start_r
    arrived = (r1 >= p.r2 * 0.97) if outward else (r1 <= p.r2 * 1.03)
    if arrived or craft.pos.distance_to(t.pos) < 60:
        p.set_mode("follow", target=t)
        return _follow(craft, bodies, sim_dt, real_dt, keys)
    p.status = f"Transfer to {t.name}: coasting ({abs(p.r2 - r1):.0f} px to go)"
    return pygame.Vector2()


# --- Save / load -------------------------------------------------------------------
def pilot_to_dict(pilot, index):
    """index(body) -> int or None."""
    hold = None
    if pilot.hold and pilot.hold[0] == "L":
        hold = ["L", index(pilot.hold[1]), index(pilot.hold[2]), pilot.hold[3]]
    elif pilot.hold:
        hold = ["orbit", index(pilot.hold[1]), pilot.hold[2]]
    return {"mode": pilot.mode, "hold": hold,
            "target": index(pilot.target) if pilot.target else None, "dv": pilot.dv}


def pilot_from_dict(d, bodies):
    p = Autopilot()
    hold = d.get("hold")
    if hold and hold[0] == "L":
        hold = ("L", bodies[hold[1]], bodies[hold[2]], hold[3])
    elif hold:
        hold = ("orbit", bodies[hold[1]], hold[2])
    target = bodies[d["target"]] if d.get("target") is not None else None
    p.set_mode(d.get("mode", "off"), target=target, hold=hold)
    p.dv = d.get("dv", 0.0)
    return p
