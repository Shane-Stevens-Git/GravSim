"""Gravity, integration, collisions and orbit math. No drawing here."""
import math

import random

import numpy as np
import pygame

from body import Body
from config import *


def accelerations(pos, mass, sources=None, soft2=None):
    """N-body gravity: a_i = sum_j G*m_j * (p_j - p_i) / (|p_j - p_i|^2 + eps_ij^2)^1.5.

    `sources` (index array) limits which bodies pull - test particles don't,
    which turns O(n^2) into O(n * k) for k massive bodies. A body's pull on
    itself is automatically zero because p_j - p_i = 0.
    `soft2` holds each body's softening length squared; a pair uses the mean,
    so forces stay symmetric (Newton's third law) and energy is conserved.
    """
    if sources is not None:
        src_pos, src_mass = pos[sources], mass[sources]
    else:
        src_pos, src_mass = pos, mass
    d = src_pos[None, :, :] - pos[:, None, :]       # d[i, j] = p_j - p_i
    if soft2 is None:
        eps2 = SOFTENING ** 2
    else:
        src_soft2 = soft2[sources] if sources is not None else soft2
        eps2 = (soft2[:, None] + src_soft2[None, :]) / 2
    dist_sq = (d * d).sum(axis=-1) + eps2
    inv_r3 = dist_sq ** -1.5
    return G * (d * (src_mass[None, :] * inv_r3)[:, :, None]).sum(axis=1)


def pack(bodies):
    """Body objects -> NumPy arrays."""
    pos = np.array([(b.pos.x, b.pos.y) for b in bodies], dtype=float).reshape(-1, 2)
    vel = np.array([(b.vel.x, b.vel.y) for b in bodies], dtype=float).reshape(-1, 2)
    mass = np.array([b.mass for b in bodies], dtype=float)
    movable = np.array([0.0 if b.fixed else 1.0 for b in bodies])[:, None]
    return pos, vel, mass, movable


def verlet(pos, vel, acc, mass, movable, dt, sources=None, soft2=None):
    """One velocity-Verlet step, in place. Returns the new accelerations."""
    pos += movable * (vel * dt + 0.5 * acc * dt * dt)
    new_acc = accelerations(pos, mass, sources, soft2)
    vel += movable * (0.5 * (acc + new_acc) * dt)
    return new_acc


def find_collisions(pos, vel, radii, mode, cols=None, particle=None, absorbs=None):
    """Sorted index pairs (i, j), i < j, of overlapping bodies.

    `cols` (index array of regular bodies) restricts checks to pairs that
    involve at least one regular body: test particles never hit each other.
    In bounce mode only pairs still moving toward each other count, so a
    pair that has already bounced isn't hit again while separating.
    """
    if cols is None:
        cols = np.arange(len(pos))
    d = pos[cols][None, :, :] - pos[:, None, :]     # d[i, c] = p_cols[c] - p_i
    dist = np.hypot(d[..., 0], d[..., 1])
    hit = dist < (radii[:, None] + radii[cols][None, :])
    if mode == "bounce":
        approaching = ((vel[cols][None, :, :] - vel[:, None, :]) * d).sum(axis=-1) < 0
        hit &= approaching
    if particle is not None and absorbs is not None and not absorbs.all():
        # Test particles fly through bodies that don't absorb them (galaxy cores)
        hit &= ~(particle[:, None] & ~absorbs[cols][None, :])
    ii, cc = np.nonzero(hit)
    pairs = {(min(i, j), max(i, j)) for i, j in zip(ii.tolist(), cols[cc].tolist()) if i != j}
    return sorted(pairs)


def merge(a, b):
    """Perfectly inelastic collision: b is absorbed into a.

    Conserves mass and momentum; the merged body sits at the combined
    center of mass and keeps the combined volume (radius^3 adds up).
    """
    m = a.mass + b.mass
    if a.fixed or b.fixed:
        anchor = a if a.fixed else b
        a.pos.update(anchor.pos)
        a.vel.update(0, 0)
        a.fixed = True
    else:
        a.pos = (a.pos * a.mass + b.pos * b.mass) / m
        a.vel = (a.vel * a.mass + b.vel * b.mass) / m
    if a.kind == "blackhole" or b.kind == "blackhole":
        a.kind, a.color = "blackhole", (0, 0, 0)     # anything + black hole = black hole
    else:
        a.color = tuple(int((ca * a.mass + cb * b.mass) / m) for ca, cb in zip(a.color, b.color))
    a.radius = max(2, round((a.radius ** 3 + b.radius ** 3) ** (1 / 3)))
    a.particle = a.particle and b.particle      # absorbing a real body makes it real
    a.soft = max(a.soft, b.soft)
    a.mass = m


def bounce(a, b):
    """Collision with restitution: impulse along the line of centers,
    plus pushing the bodies apart so they no longer overlap."""
    inv_a = 0.0 if a.fixed else 1.0 / a.mass
    inv_b = 0.0 if b.fixed else 1.0 / b.mass
    if inv_a + inv_b == 0:
        return
    delta = b.pos - a.pos
    dist = delta.length()
    n = delta / dist if dist > 1e-9 else pygame.Vector2(1, 0)
    rel = (b.vel - a.vel).dot(n)
    if rel < 0:
        j = -(1 + RESTITUTION) * rel / (inv_a + inv_b)
        a.vel -= n * (j * inv_a)
        b.vel += n * (j * inv_b)
    overlap = a.radius + b.radius - dist
    if overlap > 0:
        a.pos -= n * (overlap * inv_a / (inv_a + inv_b))
        b.pos += n * (overlap * inv_b / (inv_a + inv_b))


def simulate(bodies, dt, steps, mode, events=None):
    """Advance `steps` fixed steps, handling collisions. Mutates `bodies`.

    mode: "merge", "shatter" (merge, but fast impacts fragment) or "bounce".
    If `events` is a list, (kind, position, strength) tuples are appended
    for each collision - used for flashes and sounds.
    """
    done = 0
    new_bodies = []
    while done < steps and bodies:
        pos, vel, mass, movable = pack(bodies)
        radii = np.array([b.radius for b in bodies], dtype=float)
        particle = np.array([b.particle for b in bodies], dtype=bool)
        sources = np.nonzero(~particle)[0] if particle.any() else None
        soft2 = np.array([b.soft ** 2 for b in bodies], dtype=float)
        absorbs = np.array([b.absorbs for b in bodies], dtype=bool)
        acc = accelerations(pos, mass, sources, soft2)
        pairs = []
        while done < steps and not pairs:
            acc = verlet(pos, vel, acc, mass, movable, dt, sources, soft2)
            done += 1
            pairs = find_collisions(pos, vel, radii, mode, sources, particle, absorbs)
        for b, p, v in zip(bodies, pos, vel):
            b.pos.update(p[0], p[1])
            b.vel.update(v[0], v[1])
        if not pairs:
            break
        # Resolve collisions in Python, then repack and keep going.
        gone = set()
        for i, j in pairs:
            if i in gone or j in gone:
                continue
            a, b = bodies[i], bodies[j]
            speed = (a.vel - b.vel).length()
            if mode in ("merge", "shatter"):
                if b.mass > a.mass:          # heavier body survives
                    a, b = b, a
                    i, j = j, i
                point = pygame.Vector2(a.pos)
                if mode == "shatter" and should_shatter(a, b):
                    debris = shatter(a, b)
                    new_bodies.extend(debris)
                    kind = "shatter"
                else:
                    merge(a, b)
                    kind = "merge"
                gone.add(j)
                if events is not None and not (a.particle or b.particle):
                    events.append((kind, point, b.mass * speed * speed))
            else:
                bounce(a, b)
                if events is not None and not (a.particle or b.particle):
                    events.append(("bounce", (a.pos + b.pos) / 2,
                                   min(a.mass, b.mass) * speed * speed))
        if gone or new_bodies:
            bodies[:] = [b for k, b in enumerate(bodies) if k not in gone] + new_bodies
            new_bodies = []


def predict_path(bodies, start, vel0, frame_body=None, test_radius=0):
    """Preview a throw: a massless test particle flown through the n-body
    system (the heaviest bodies move during the preview too).

    If frame_body is given (the body the camera follows), the path is
    returned relative to it, so it matches what you see on screen.
    """
    heavy = sorted(bodies, key=lambda b: b.mass, reverse=True)[:PREVIEW_MAX_BODIES]
    if frame_body is not None and frame_body not in heavy:
        heavy.append(frame_body)
    k = heavy.index(frame_body) if frame_body is not None else None
    pos, vel, mass, movable = pack(heavy)
    radii = np.array([b.radius for b in heavy], dtype=float)
    frame0 = pos[k].copy() if k is not None else None
    pos = np.vstack([pos, start])
    vel = np.vstack([vel, vel0])
    mass = np.append(mass, 0.0)
    movable = np.vstack([movable, [[1.0]]])
    soft2 = np.append([b.soft ** 2 for b in heavy], SOFTENING ** 2)
    acc = accelerations(pos, mass, None, soft2)
    points = []
    for i in range(PREVIEW_STEPS):
        acc = verlet(pos, vel, acc, mass, movable, PREVIEW_DT, None, soft2)
        p = pos[-1].copy()
        if (np.hypot(*(pos[:-1] - p).T) < radii + test_radius).any():
            break                                   # would hit something
        if k is not None:
            p -= pos[k] - frame0
        if i % 3 == 0:
            points.append(p)
    return points


def orbit_info(rel_pos, rel_vel, central_mass, impact_radius):
    """Two-body orbit a launch would produce around `central_mass`.

    Returns eccentricity, whether the orbit escapes (energy >= 0), and
    whether its closest approach is inside `impact_radius`.
    """
    mu = G * central_mass
    r = rel_pos.length()
    v2 = rel_vel.length_squared()
    if r < 1e-6:
        return None
    energy = v2 / 2 - mu / r
    e_vec = ((v2 - mu / r) * rel_pos - rel_pos.dot(rel_vel) * rel_vel) / mu
    e = e_vec.length()
    if energy >= 0:
        return {"e": e, "escape": True, "impact": False}
    a = -mu / (2 * energy)
    periapsis = a * (1 - e)
    return {"e": e, "escape": False, "impact": periapsis < impact_radius}


def circular_speed(central_mass, r):
    """Speed needed for a circular orbit of radius r: v = sqrt(G*M/r)."""
    return (G * central_mass / max(r, 1e-6)) ** 0.5


def dominant_body(body, bodies):
    """The heavier body pulling hardest on `body` (what it 'orbits'), or None."""
    best, best_pull = None, 0.0
    for other in bodies:
        if other is body or other.mass <= body.mass:
            continue
        d2 = max((other.pos - body.pos).length_squared(), 1e-6)
        pull = other.mass / d2
        if pull > best_pull:
            best, best_pull = other, pull
    return best


def orbital_elements(rel_pos, rel_vel, mu):
    """Two-body (Keplerian) orbit from relative position/velocity.

    mu = G * (M + m). Returns a dict with eccentricity e, semi-latus rectum p,
    periapsis direction omega (radians), periapsis/apoapsis distances,
    semi-major axis a and period (None when unbound), and `bound`.
    """
    r = rel_pos.length()
    if r < 1e-9 or mu <= 0:
        return None
    v2 = rel_vel.length_squared()
    energy = v2 / 2 - mu / r
    e_vec = ((v2 - mu / r) * rel_pos - rel_pos.dot(rel_vel) * rel_vel) / mu
    e = e_vec.length()
    h = rel_pos.x * rel_vel.y - rel_pos.y * rel_vel.x      # specific angular momentum
    p = h * h / mu
    omega = math.atan2(e_vec.y, e_vec.x) if e > 1e-9 else math.atan2(rel_pos.y, rel_pos.x)
    bound = energy < 0 and e < 1
    a = -mu / (2 * energy) if bound else None
    return {
        "e": e, "p": p, "omega": omega, "bound": bound, "a": a,
        "period": 2 * math.pi * math.sqrt(a ** 3 / mu) if bound else None,
        "periapsis": p / (1 + e),
        "apoapsis": p / (1 - e) if bound else None,
    }


def orbit_points(el, n=180, max_r=20_000):
    """Points (relative to the primary) along the conic described by `el`.
    Ellipse for bound orbits, the outgoing/incoming hyperbola arm otherwise."""
    if el is None or el["p"] < 1e-6:
        return []                                  # radial fall: no conic to draw
    e, p, w = el["e"], el["p"], el["omega"]
    if el["bound"]:
        thetas = [2 * math.pi * i / n for i in range(n + 1)]
    else:
        lim = math.acos(max(-1.0, -1.0 / e)) - 1e-3 if e > 1 else math.pi - 1e-3
        thetas = [-lim + 2 * lim * i / n for i in range(n + 1)]
    pts = []
    for t in thetas:
        denom = 1 + e * math.cos(t)
        if denom <= 1e-9:
            continue
        r = p / denom
        if r > max_r:
            continue
        pts.append((r * math.cos(t + w), r * math.sin(t + w)))
    return pts


def strongest_pull_at(point, bodies):
    """The body whose gravity is strongest at `point` (for auto-orbit placement)."""
    best, best_pull = None, 0.0
    for b in bodies:
        pull = b.mass / max((b.pos - point).length_squared(), 1e-6)
        if pull > best_pull:
            best, best_pull = b, pull
    return best


def hill_radius(body, primary):
    """Rough radius inside which `body` can hold its own moons against
    `primary`'s tides: r_H = d * (m / 3M)^(1/3). Stable orbits sit well
    inside it (about half)."""
    d = body.pos.distance_to(primary.pos)
    return d * (body.mass / (3 * primary.mass)) ** (1 / 3)


def system_energy(bodies):
    """(kinetic, potential, momentum Vector2) of the regular bodies.

    Test particles are left out: they exert no gravity, so they're not part
    of the conserved system. The potential uses the same softening as the
    force, so with no collisions total energy should stay constant - the
    graph shows how well the integrator does, and the steps where
    inelastic merges turn motion into (unmodelled) heat.
    """
    real = [b for b in bodies if not b.particle]
    if not real:
        return 0.0, 0.0, pygame.Vector2()
    pos, vel, mass, _ = pack(real)
    soft2 = np.array([b.soft ** 2 for b in real], dtype=float)
    ke = 0.5 * float((mass * (vel ** 2).sum(axis=1)).sum())
    d = pos[None, :, :] - pos[:, None, :]
    r = np.sqrt((d * d).sum(axis=-1) + (soft2[:, None] + soft2[None, :]) / 2)
    iu = np.triu_indices(len(real), k=1)
    pe = -float((G * mass[:, None] * mass[None, :] / r)[iu].sum())
    p = (vel * mass[:, None]).sum(axis=0)
    return ke, pe, pygame.Vector2(float(p[0]), float(p[1]))



# --- Destruction (SHATTER mode) ------------------------------------------------------
def should_shatter(a, b):
    """Impacts much faster than the pair's mutual escape speed fragment
    instead of merging. Pinned bodies and test particles always just merge."""
    if a.fixed or b.fixed or a.particle or b.particle:
        return False
    v_esc = math.sqrt(2 * G * (a.mass + b.mass) / (a.radius + b.radius))
    return (a.vel - b.vel).length() > SHATTER_SPEED * v_esc


def shatter(big, small, rng=random):
    """Fragmenting impact. `big` survives as the largest remnant (updated in
    place); returns the debris as test particles. Mass and momentum are
    conserved exactly: the remnant's velocity is whatever balances the debris."""
    total = big.mass + small.mass
    momentum = big.vel * big.mass + small.vel * small.mass
    v_cm = momentum / total
    v_esc = math.sqrt(2 * G * total / (big.radius + small.radius))
    excess = (big.vel - small.vel).length() / (SHATTER_SPEED * v_esc)   # > 1
    keep = min(max(1.1 - 0.35 * excess, 0.2), 0.85)     # harder hit -> smaller remnant
    color = tuple(int((ca * big.mass + cb * small.mass) / total)
                  for ca, cb in zip(big.color, small.color))
    center = (big.pos * big.mass + small.pos * small.mass) / total
    normal = small.pos - big.pos
    normal = normal.normalize() if normal.length() > 1e-9 else pygame.Vector2(1, 0)
    r_left = max(2, round(((big.radius ** 3 + small.radius ** 3) * keep) ** (1 / 3)))

    debris_mass = total * (1 - keep)
    n = int(min(max(debris_mass / (total * 0.02), SHATTER_MIN_PIECES), SHATTER_MAX_PIECES))
    pieces, p_debris = [], pygame.Vector2()
    for k in range(n):
        direction = normal.rotate(rng.uniform(-75, 75))       # spray from the impact side
        v = v_cm + direction * v_esc * rng.uniform(0.5, 1.3)
        piece = Body(center + direction * (r_left + 3 + rng.uniform(0, 4)), debris_mass / n,
                     rng.choice((1, 1, 2)), color, vel=v, name="Debris", particle=True)
        pieces.append(piece)
        p_debris += v * piece.mass

    big.mass = total * keep
    big.radius = r_left
    big.color = color
    big.pos = center
    big.vel = (momentum - p_debris) / big.mass
    return pieces


def roche_limit(body, primary):
    """Distance inside which `primary`'s tides tear `body` apart:
    d = k * r_body * (M / m)^(1/3) (k = 2.44 for a fluid body; we use a
    smaller k since sandbox densities are arbitrary)."""
    return ROCHE_COEFF * body.radius * (primary.mass / body.mass) ** (1 / 3)


def tidal_victims(bodies):
    """(victim, primary) pairs where a body is inside the Roche limit of the
    heavier body it orbits. Only real, reasonably sized bodies can break up."""
    out = []
    for b in bodies:
        if b.particle or b.fixed or b.radius < ROCHE_MIN_RADIUS:
            continue
        primary = dominant_body(b, bodies)
        if (primary is not None and primary.mass > 10 * b.mass
                and b.pos.distance_to(primary.pos) < roche_limit(b, primary)):
            out.append((b, primary))
    return out


def tidal_disrupt(body, rng=random):
    """Replace `body` with a clump of debris particles occupying its volume,
    each moving with the body's velocity plus a little spread. The primary's
    tides then stretch the clump into a stream along the orbit."""
    n = int(min(max(body.radius * 4, 12), 40))
    pieces = []
    for k in range(n):
        offset = pygame.Vector2(rng.uniform(0, body.radius), 0).rotate(rng.uniform(0, 360))
        jitter = pygame.Vector2(rng.gauss(0, 1), rng.gauss(0, 1)) * body.vel.length() * 0.01
        pieces.append(Body(body.pos + offset, body.mass / n, rng.choice((1, 1, 2)),
                           body.color, vel=body.vel + jitter, name="Debris", particle=True))
    return pieces
