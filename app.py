"""The GravSim application: state, input handling and drawing."""
import math
import os
import random
from collections import deque

import pygame

import ui
from body import Body, View
from config import *
from craft import make_craft, steer
from effects import Flashes, Starfield
from field import FieldOverlay
from history import History
from physics import (circular_speed, dominant_body, orbit_info, orbit_points,
                     orbital_elements, predict_path, simulate, strongest_pull_at,
                     system_energy, tidal_disrupt, tidal_victims)
from render import draw_arrow, draw_points
from sound import Sound
from scenes import (QUICKSAVE, SCENARIOS, ask_path, lagrange_points, load_file,
                    place_in_orbit, ring_around, save_file, to_dict)


ARROW_KEYS = {pygame.K_UP: "up", pygame.K_DOWN: "down",
              pygame.K_LEFT: "left", pygame.K_RIGHT: "right"}


class App:
    """Owns the simulation state, input handling and drawing."""

    def __init__(self):
        pygame.init()
        self.windowed_size = self.initial_size()
        self.fullscreen = False
        self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        pygame.display.set_caption("GravSim")
        self.clock = pygame.time.Clock()
        self.hud = ui.HUD(*self.screen.get_size())
        self.starfield = Starfield()
        self.flashes = Flashes()
        self.sound = Sound()
        self.view = View(self.screen.get_size())

        self.preset_idx = 2         # start on "Planet"
        self.size_mult = self.mass_mult = 1.0
        self.drag_start = None      # screen position of mouse-down while aiming
        self.slider = None          # (name, track rect) while dragging a slider
        self.selection = None       # the body shown in the inspector
        self.show_preview = True
        self.show_trails = True
        self.follow = True          # camera keeps self.target centered
        self.mode = "merge"         # collision mode: "merge" or "bounce"
        self.paused = False
        self.speed_idx = DEFAULT_SPEED_IDX
        self.step_request = 0       # frames to advance while paused (N key)
        self.running = True
        self.accumulator = 0.0
        self.sim_time = 0.0
        self.lagrange = None        # (primary, secondary) whose L-points are marked
        self.show_lagrange = False
        self.toast = None           # (text, expiry in ms)
        self.n_particles = 0
        self.events = []            # collisions this frame: (kind, pos, strength)
        self.keys_held = set()      # arrow keys held (manual spacecraft piloting)
        self.pick = None            # (craft, mode) while waiting for a target click
        self.select_tool = False    # Q: clicks select (nearest body), drags pan
        self.select_press = None    # mouse-down position while using the select tool
        self.select_panned = False
        self.history = History()    # rewind buffer
        self.rng = random.Random(SIM_SEED)   # debris randomness (seeded: repeatable)
        self.rewinding = False      # Z held
        self.orbit_tool = False     # O: a click places a body on a circular orbit
        self.field = FieldOverlay()
        self.show_field = False     # W: gravity field overlay
        self.show_energy = False    # E: energy & momentum graph
        self.energy_log = deque(maxlen=int(ENERGY_WINDOW / ENERGY_SAMPLE))
        self.energy_scales = (1.0, 1.0)
        self.next_energy = 0.0
        self.scenario_idx = 0
        self.reset_source = ("scenario", 0)
        self.start_scenario(0)

    # --- Window ---------------------------------------------------------------------------
    @staticmethod
    def initial_size():
        """Default window size, shrunk to fit smaller desktops."""
        info = pygame.display.Info()
        w, h = WIDTH, HEIGHT
        if info.current_w > 0 and info.current_h > 0:
            w = min(w, int(info.current_w * 0.95))
            h = min(h, int(info.current_h * 0.9))
        return max(w, MIN_WINDOW[0]), max(h, MIN_WINDOW[1])

    def on_resize(self, size=None):
        """Window changed size: re-layout panels and the camera."""
        if size is not None and not self.fullscreen:
            w, h = max(size[0], MIN_WINDOW[0]), max(size[1], MIN_WINDOW[1])
            if (w, h) != tuple(size):             # too small: snap back to the minimum
                pygame.display.set_mode((w, h), pygame.RESIZABLE)
            self.windowed_size = (w, h)
        self.screen = pygame.display.get_surface()
        self.hud.w, self.hud.h = self.screen.get_size()
        self.view.resize(self.screen.get_size())

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.on_resize()

    # --- State helpers -----------------------------------------------------------
    @property
    def following(self):
        return self.follow and self.target in self.bodies

    def set_sun(self, body):
        """Make `body` the main body (sun panel, HUD reference)."""
        old = getattr(self, "sun", None)
        self.sun = body
        body.trail = deque(maxlen=SUN_TRAIL_LENGTH)
        if getattr(self, "target", None) in (None, old) or self.target not in self.bodies:
            self.set_target(body)

    def set_target(self, body):
        """Body the camera follows. Trails are stored relative to it, so they reset."""
        if getattr(self, "target", None) is not body:
            self.target = body
            self.clear_trails()

    # --- Scenes ---------------------------------------------------------------------
    def load_scene(self, sc):
        """Install a scene dict (see scenes.py)."""
        bodies = sc["bodies"]
        self.bodies = bodies
        self.selection = None
        self.sun = self.target = None
        self.set_sun(bodies[sc["sun"]])
        t = sc["target"]
        self.follow = t is not None
        if t is not None:
            self.set_target(bodies[t])
        self.view.center = pygame.Vector2(self.target.pos if self.follow else sc["center"])
        self.view.zoom = sc["zoom"]
        lg = sc.get("lagrange")
        self.lagrange = (bodies[lg[0]], bodies[lg[1]]) if lg else None
        self.show_lagrange = self.lagrange is not None
        if sc.get("mode"):
            self.mode = sc["mode"]
        self.sim_time = sc.get("sim_time", 0.0)
        self.accumulator = 0.0
        self.history.clear(self.sim_time)
        self.rng = random.Random(SIM_SEED)
        self.reset_energy_log()
        self.clear_trails()

    def sun_settings(self):
        """(mass, radius, color, kind) and pinned state of the current sun, so
        scenarios rebuilt with R or picked from the menu keep sun-panel edits."""
        sun = getattr(self, "sun", None)
        if sun is None or sun.name != "Sun":
            _name, *cfg = SUN_TYPES[DEFAULT_SUN]
            return tuple(cfg), False
        return (sun.mass, sun.radius, sun.color, sun.kind), sun.fixed

    def start_scenario(self, i):
        cfg, fixed = self.sun_settings()
        name, _desc, build = SCENARIOS[i]
        self.load_scene(build(cfg, fixed))
        self.scenario_idx = i
        self.reset_source = ("scenario", i)
        self.hud.scenes_open = False
        return name

    def reset(self):
        """R: rebuild the current scenario, or reload the last loaded file."""
        kind, arg = self.reset_source
        if kind == "file":
            self.load_scene_file(arg, quiet=True)
        else:
            self.start_scenario(arg)

    def current_scene(self):
        return {"bodies": self.bodies, "sun": self.sun,
                "target": self.target if self.following else None,
                "center": self.view.center, "zoom": self.view.zoom,
                "lagrange": ([self.bodies.index(b) for b in self.lagrange]
                             if self.lagrange else None),
                "mode": self.mode}

    def save_scene(self, path=None):
        path = path or ask_path(save=True)
        if not path:
            return
        try:
            save_file(to_dict(self.current_scene(), {"sim_time": self.sim_time}), path)
            self.notify(f"Saved {os.path.basename(path)}")
        except OSError as e:
            self.notify(f"Couldn't save: {e.strerror or e}")

    def load_scene_file(self, path=None, quiet=False):
        path = path or ask_path(save=False)
        if not path:
            return
        try:
            self.load_scene(load_file(path))
        except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
            self.notify(f"Couldn't load {os.path.basename(path)}: {e}")
            return
        self.reset_source = ("file", path)
        self.scenario_idx = None
        self.hud.scenes_open = False
        if not quiet:
            self.notify(f"Loaded {os.path.basename(path)}")

    def notify(self, text, ms=2500):
        self.toast = (text, pygame.time.get_ticks() + ms)

    def toggle_lagrange(self):
        """K: show L1-L5 for the selected body and what it orbits (or the
        scene's pair / the sun and the heaviest other body)."""
        if self.show_lagrange:
            self.show_lagrange = False
            return
        sel = self.selection
        primary = dominant_body(sel, self.bodies) if sel is not None else None
        if primary is not None:
            self.lagrange = (primary, sel)
        elif self.lagrange is None or any(b not in self.bodies for b in self.lagrange):
            others = [b for b in self.bodies if b is not self.sun]
            self.lagrange = ((self.sun, max(others, key=lambda b: b.mass))
                             if others and self.sun in self.bodies else None)
        self.show_lagrange = self.lagrange is not None
        if not self.show_lagrange:
            self.notify("Lagrange points need two bodies")

    def clear_trails(self):
        for b in getattr(self, "bodies", []):
            b.trail.clear()

    def remove_body(self, body):
        self.bodies = [b for b in self.bodies if b is not body]
        self.after_removals()

    def after_removals(self):
        """Fix up references after bodies merged, were culled or deleted."""
        if self.selection not in self.bodies:
            self.selection = None
        if self.pick and self.pick[0] not in self.bodies:
            self.pick = None
        if self.lagrange and any(b not in self.bodies for b in self.lagrange):
            self.lagrange, self.show_lagrange = None, False
        if self.sun not in self.bodies and self.bodies:   # sun swallowed or flung away
            self.set_sun(max(self.bodies, key=lambda b: b.mass))
        if self.target not in self.bodies and self.sun in self.bodies:
            self.set_target(self.sun)

    def select_preset(self, i):
        self.select_tool = False
        self.preset_idx = i
        self.size_mult = self.mass_mult = 1.0

    def preset_body(self):
        """(name, mass, radius, color) of the body the next throw will create."""
        name, mass, radius, color = PRESETS[self.preset_idx]
        r = max(2, round(radius * self.size_mult))
        m = mass * self.size_mult ** 3 * self.mass_mult   # size keeps density; Shift changes it
        return name, m, r, color

    def launch_velocity(self, mouse):
        """Drag vector -> velocity. Measured in world pixels, so a drag means
        the same speed at every zoom level (the arrow = ~1 s of travel)."""
        v = (pygame.Vector2(mouse) - self.drag_start) * (LAUNCH_SCALE / self.view.zoom)
        return -v if SLINGSHOT else v

    def zoom(self, factor, screen_pos=None):
        # While following, the target is locked to the center, so zoom about it.
        self.view.zoom_by(factor, None if self.following else screen_pos)

    @property
    def speed(self):
        return TIME_SPEEDS[self.speed_idx]

    def change_speed(self, delta, wrap=False):
        n = len(TIME_SPEEDS)
        i = self.speed_idx + delta
        self.speed_idx = i % n if wrap else min(max(i, 0), n - 1)

    @property
    def crowded(self):
        """Lots of test particles: draw them as dots, skip their trails."""
        return self.n_particles > PARTICLE_TRAIL_LIMIT

    def body_at(self, screen_pos):
        """Topmost body under a screen position (with a few px of slack)."""
        best, best_d = None, None
        crowded = self.crowded
        for b in self.bodies:
            if crowded and b.particle:
                continue
            p = self.view.to_screen(b.pos)
            reach = max(b.radius * self.view.zoom, 6) + 4
            d = p.distance_to(screen_pos)
            if d <= reach and (best_d is None or d < best_d):
                best, best_d = b, d
        return best

    def nearest_body(self, screen_pos, radius=SELECT_RADIUS):
        """Forgiving pick: the body whose edge is nearest the click, within
        `radius` screen px. Regular bodies win over particles (dust, debris)."""
        best, best_key = None, None
        crowded = self.crowded
        for b in self.bodies:
            if crowded and b.particle:
                continue
            gap = self.view.to_screen(b.pos).distance_to(screen_pos) - b.radius * self.view.zoom
            if gap <= radius:
                key = (b.particle, max(gap, 0))
                if best_key is None or key < best_key:
                    best, best_key = b, key
        return best

    # --- Selection -----------------------------------------------------------------
    def toggle_follow_selection(self):
        sel = self.selection
        if sel is None:
            return
        if self.following and self.target is sel:
            self.set_target(self.sun)           # back to the sun
        else:
            self.set_target(sel)
            self.follow = True

    def scale_selection_mass(self, factor):
        if self.selection is not None:
            self.selection.mass = max(0.01, self.selection.mass * factor)

    def selection_info(self):
        sel = self.selection
        primary = dominant_body(sel, self.bodies)
        if primary is not None:
            rel_pos, rel_vel = sel.pos - primary.pos, sel.vel - primary.vel
            el = orbital_elements(rel_pos, rel_vel, G * (primary.mass + sel.mass))
            dist, speed = rel_pos.length(), rel_vel.length()
        else:
            el, dist, speed = None, None, sel.vel.length()
        return primary, el, {
            "name": sel.name, "color": sel.color, "accent": sel.accent, "kind": sel.kind,
            "mass": sel.mass, "primary": primary.name if primary else None,
            "speed": speed, "dist": dist, "el": el,
            "following": self.following and self.target is sel,
            "craft": None if sel.pilot is None else {
                "mode": sel.pilot.mode, "status": sel.pilot.status, "dv": sel.pilot.dv,
                "picking": self.pick[1] if self.pick and self.pick[0] is sel else None},
        }

    # --- Spacecraft --------------------------------------------------------------------
    def set_pilot_mode(self, mode):
        craft = self.selection
        if craft is None or craft.pilot is None:
            return
        self.pick = None
        craft.pilot.itinerary = []              # a manual command ends any tour
        if mode in ("transfer", "follow"):
            self.pick = (craft, mode)
            craft.pilot.status = ("Click the body to transfer to" if mode == "transfer"
                                  else "Click the body to rendezvous with")
            self.notify(craft.pilot.status + " (click empty space to cancel)")
        elif mode == "hold":
            hold = self.hold_target(craft)
            if hold is None:
                self.notify("Nothing to hold on to here")
                return
            craft.pilot.set_mode("hold", hold=hold)
        else:
            craft.pilot.set_mode(mode)

    def hold_target(self, craft):
        """Hold the nearest shown Lagrange point if we're close to one,
        otherwise hold a circular orbit at the current distance."""
        if self.show_lagrange and self.lagrange:
            label, point = min(lagrange_points(*self.lagrange).items(),
                               key=lambda kv: kv[1].distance_to(craft.pos))
            if point.distance_to(craft.pos) < 100:
                return ("L", *self.lagrange, label)
        primary = dominant_body(craft, self.bodies)
        if primary is None:
            return None
        return ("orbit", primary, craft.pos.distance_to(primary.pos))

    def pick_target(self, pos):
        """Second click of Transfer/Follow: choose the target body."""
        craft, mode = self.pick
        self.pick = None
        hit = self.nearest_body(pos)
        if hit is None or hit is craft:
            craft.pilot.status = "Autopilot " + craft.pilot.mode
            self.notify("Target selection cancelled")
            return
        craft.pilot.set_mode(mode, target=hit)
        self.notify(f"{craft.name}: {'transfer to' if mode == 'transfer' else 'rendezvous with'} {hit.name}")

    # --- Sun controls --------------------------------------------------------------
    def sun_type_index(self):
        s = self.sun
        for i, (_n, m, r, c, kind) in enumerate(SUN_TYPES):
            if (abs(s.mass - m) < 0.5 and s.radius == r and s.kind == kind
                    and (kind == "blackhole" or s.color == c)):
                return i
        return None

    def apply_sun_type(self, i):
        _name, m, r, c, kind = SUN_TYPES[i]
        s = self.sun
        s.mass, s.radius, s.color, s.kind = float(m), r, c, kind

    def recenter(self):
        """Shift the whole system so the sun sits at the view center, at rest.
        This is only a change of reference frame - relative motion is kept."""
        if self.sun not in self.bodies:
            return
        if self.following:                      # camera will center on the sun itself
            self.set_target(self.sun)
            shift = pygame.Vector2(0, 0)
        else:
            shift = self.view.center - self.sun.pos
        v = pygame.Vector2(self.sun.vel)
        for b in self.bodies:
            b.pos += shift
            if not b.fixed:
                b.vel -= v
        self.clear_trails()

    def update_slider(self, pos):
        name, track = self.slider
        t = min(max((pos[0] - track.x) / track.width, 0.0), 1.0)
        if name == "sun_mass":
            lo, hi = SUN_MASS_RANGE
            self.sun.mass = float(f"{lo * (hi / lo) ** t:.3g}")   # 3 significant figures
        elif name == "sun_radius":
            lo, hi = SUN_RADIUS_RANGE
            self.sun.radius = round(lo + (hi - lo) * t)

    # --- Input ---------------------------------------------------------------------
    def handle_key(self, k):
        ctrl = pygame.key.get_mods() & pygame.KMOD_CTRL
        if ctrl and k == pygame.K_s:
            self.save_scene()
        elif ctrl and k == pygame.K_o:
            self.load_scene_file()
        elif k == pygame.K_F11:
            self.toggle_fullscreen()
        elif k == pygame.K_F5:
            self.save_scene(QUICKSAVE)
        elif k == pygame.K_F9:
            if os.path.exists(QUICKSAVE):
                self.load_scene_file(QUICKSAVE)
            else:
                self.notify("No quicksave yet (F5 to make one)")
        elif k in ARROW_KEYS:
            self.keys_held.add(ARROW_KEYS[k])
        elif k == pygame.K_ESCAPE and self.pick:
            self.pick[0].pilot.status = "Autopilot " + self.pick[0].pilot.mode
            self.pick = None
        elif k == pygame.K_ESCAPE:
            if self.hud.scenes_open:
                self.hud.scenes_open = False
            else:
                self.running = False
        elif k == pygame.K_p:
            self.hud.scenes_open = not self.hud.scenes_open
        elif self.hud.scenes_open and pygame.K_1 <= k < pygame.K_1 + len(SCENARIOS):
            self.notify(f"Scene: {self.start_scenario(k - pygame.K_1)}")
        elif k == pygame.K_k:
            self.toggle_lagrange()
        elif k == pygame.K_q:
            self.select_tool = not self.select_tool
        elif k == pygame.K_z:
            self.rewinding = True
        elif k == pygame.K_o:
            self.orbit_tool = not self.orbit_tool
        elif k == pygame.K_x:
            if not self.sound.available:
                self.notify("No audio device found - sound unavailable")
            else:
                self.notify("Sound on" if self.sound.toggle() else "Sound off")
        elif k == pygame.K_w:
            self.show_field = not self.show_field
        elif k == pygame.K_e:
            self.show_energy = not self.show_energy
            self.reset_energy_log()
        elif k == pygame.K_b:
            self.add_ring()
        elif k == pygame.K_SPACE:
            self.paused = not self.paused
        elif k == pygame.K_n:                   # step one frame (pauses first)
            self.paused = True
            self.step_request += 1
        elif k in (pygame.K_PERIOD, pygame.K_GREATER):
            self.change_speed(+1)
        elif k in (pygame.K_COMMA, pygame.K_LESS):
            self.change_speed(-1)
        elif k == pygame.K_h:
            if self.selection is not None:      # panel is compact: H shows it again
                self.selection = None
                self.hud.show_help = True
            else:
                self.hud.show_help = not self.hud.show_help
        elif k == pygame.K_s:
            self.hud.sun_collapsed = not self.hud.sun_collapsed
        elif k == pygame.K_t:
            self.show_preview = not self.show_preview
        elif k == pygame.K_l:
            self.show_trails = not self.show_trails
            self.clear_trails()
        elif k == pygame.K_m:
            modes = COLLISION_MODES
            self.mode = modes[(modes.index(self.mode) + 1) % len(modes)]
        elif k == pygame.K_v:
            self.follow = not self.follow
            self.clear_trails()                 # old trails were in the old frame
        elif k == pygame.K_g:
            self.toggle_follow_selection()
        elif k in (pygame.K_DELETE, pygame.K_BACKSPACE):
            if self.selection is not None:
                self.remove_body(self.selection)
        elif k == pygame.K_LEFTBRACKET:
            self.scale_selection_mass(1 / 1.5)
        elif k == pygame.K_RIGHTBRACKET:
            self.scale_selection_mass(1.5)
        elif k == pygame.K_f:
            if self.sun in self.bodies:
                self.sun.fixed = not self.sun.fixed
                self.sun.vel.update(0, 0)
        elif k == pygame.K_c:
            self.bodies = [b for b in self.bodies if b is self.sun]
            self.after_removals()
        elif k == pygame.K_r:
            self.reset()
        elif k in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self.zoom(ZOOM_STEP)
        elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.zoom(1 / ZOOM_STEP)
        elif k in (pygame.K_0, pygame.K_KP0):
            self.view.zoom = 1.0
        elif pygame.K_1 <= k < pygame.K_1 + len(PRESETS):
            self.select_preset(k - pygame.K_1)

    def handle_action(self, action, ref, pos):
        """A click on a UI element (see ui.HUD.add)."""
        kind, arg = action
        if kind == "key":
            self.handle_key(arg)
        elif kind == "preset":
            self.select_preset(arg)
        elif kind == "sun_type":
            self.apply_sun_type(arg)
        elif kind == "speed":
            self.change_speed(+1, wrap=True)
        elif kind == "sun_recenter":
            self.recenter()
        elif kind == "slider":
            self.slider = (arg, ref)
            self.update_slider(pos)
        elif kind == "sel_close":
            self.selection = None
        elif kind == "sel_follow":
            self.toggle_follow_selection()
        elif kind == "sel_delete":
            if self.selection is not None:
                self.remove_body(self.selection)
        elif kind == "sel_mass":
            self.scale_selection_mass(arg)
        elif kind == "sel_color" and self.selection is not None:
            if self.selection.kind == "blackhole":
                self.selection.ring_color = tuple(arg)
            else:
                self.selection.color = tuple(arg)
        elif kind == "select_tool":
            self.select_tool = not self.select_tool
        elif kind == "pilot":
            self.set_pilot_mode(arg)
        elif kind == "sel_ring":
            self.add_ring()
        elif kind == "rewind":
            self.rewind(arg)
        elif kind == "scene":
            self.notify(f"Scene: {self.start_scenario(arg)}")
        elif kind == "save":
            self.save_scene()
        elif kind == "load":
            self.load_scene_file()

    def throw(self, pos):
        name, m, r, color = self.preset_body()
        vel = self.launch_velocity(pos)
        if self.following:                      # throw relative to the target's motion
            vel += self.target.vel
        body = Body(self.view.to_world(self.drag_start), m, r, color, vel=vel, name=name)
        self.bodies.append(body)
        if name == "Spacecraft":
            make_craft(body)
            self.selection = body               # open its autopilot straight away
        self.drag_start = None

    def release(self, pos):
        """Left button released after pressing on empty space: a short click
        selects a body (or, with the orbit tool, places one in orbit, or
        deselects); a real drag throws."""
        if pygame.Vector2(pos).distance_to(self.drag_start) < CLICK_SLOP:
            self.drag_start = None
            if self.pick:
                self.pick_target(pos)
                return
            hit = self.body_at(pos)
            if hit is None and self.orbit_tool:
                self.place_orbiting(pos)
            else:
                self.selection = hit
        else:
            self.throw(pos)

    def place_orbiting(self, screen_pos):
        """Orbit tool: put the next body on a circular orbit around whatever
        pulls hardest at the click (Shift+click: the other direction)."""
        name, m, r, color = self.preset_body()
        reverse = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        body, primary = place_in_orbit(self.view.to_world(screen_pos), self.bodies,
                                       m, r, color, name, reverse)
        if body is None:
            self.notify("Too close - that would be inside it")
        else:
            self.bodies.append(body)
            if name == "Spacecraft":
                make_craft(body)
                self.selection = body

    def add_ring(self):
        center = self.selection or (self.target if self.following else self.sun)
        if center not in self.bodies:
            return
        ring, msg = ring_around(center, self.bodies)
        self.bodies.extend(ring)
        self.notify(msg)

    def tidal_check(self):
        """SHATTER mode: bodies inside a heavier body's Roche limit break up."""
        for victim, primary in tidal_victims(self.bodies):
            debris = tidal_disrupt(victim, self.rng)
            self.bodies = [b for b in self.bodies if b is not victim] + debris
            self.events.append(("tidal", pygame.Vector2(victim.pos),
                                victim.mass * victim.vel.length_squared(), victim.mass))
            self.notify(f"{victim.name} was torn apart by {primary.name}'s tides")
        self.after_removals()

    def reset_energy_log(self):
        self.energy_log.clear()
        self.next_energy = self.sim_time

    def sample_energy(self):
        if self.sim_time < self.next_energy:
            return
        self.next_energy = self.sim_time + ENERGY_SAMPLE
        ke, pe, p = system_energy(self.bodies)
        self.energy_log.append((self.sim_time, ke + pe, p.length()))
        real = [b for b in self.bodies if not b.particle]
        self.energy_scales = (abs(ke) + abs(pe) or 1.0,
                              sum(b.mass * b.vel.length() for b in real) or 1.0)

    def rewind(self, snapshots=1):
        """Step back `snapshots` entries in the rewind buffer."""
        snap = None
        for _ in range(snapshots):
            snap = self.history.rewind(self.rng) or snap
        if snap is None:
            return False
        self.sim_time, self.bodies, sun, target = snap
        self.sun, self.target = sun, target
        self.accumulator = 0.0
        self.reset_energy_log()
        self.after_removals()
        self.clear_trails()
        return True

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                self.on_resize((event.w, event.h))
            elif event.type == pygame.KEYDOWN:
                self.handle_key(event.key)
            elif event.type == pygame.KEYUP and event.key == pygame.K_z:
                self.rewinding = False
            elif event.type == pygame.KEYUP and event.key in ARROW_KEYS:
                self.keys_held.discard(ARROW_KEYS[event.key])
            elif event.type == pygame.MOUSEWHEEL:
                mods = pygame.key.get_mods()
                if mods & pygame.KMOD_CTRL:
                    self.zoom(ZOOM_STEP ** event.y, pygame.mouse.get_pos())
                else:
                    f = SCROLL_STEP ** event.y
                    if mods & pygame.KMOD_SHIFT:
                        self.mass_mult = min(max(self.mass_mult * f, MASS_RANGE[0]), MASS_RANGE[1])
                    else:
                        self.size_mult = min(max(self.size_mult * f, SIZE_RANGE[0]), SIZE_RANGE[1])
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    hit = self.hud.hit(event.pos)
                    if hit:
                        self.handle_action(*hit, event.pos)
                    elif not self.hud.blocked(event.pos):
                        if self.select_tool:
                            self.select_press = pygame.Vector2(event.pos)
                            self.select_panned = False
                        else:
                            self.drag_start = pygame.Vector2(event.pos)
                elif event.button == 3:
                    self.drag_start = None
            elif event.type == pygame.MOUSEMOTION:
                if self.slider:
                    self.update_slider(event.pos)
                elif (event.buttons[1] or (self.select_press is not None and event.buttons[0]
                                           and (self.select_panned or pygame.Vector2(event.pos)
                                                .distance_to(self.select_press) >= CLICK_SLOP))):
                    # middle-drag (or a drag with the select tool) pans the view
                    if self.select_press is not None:
                        self.select_panned = True
                    if self.follow:
                        self.follow = False
                        self.clear_trails()
                    self.view.center -= pygame.Vector2(event.rel) / self.view.zoom
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.slider:
                    self.slider = None
                elif self.select_press is not None:
                    if not self.select_panned:
                        if self.pick:
                            self.pick_target(event.pos)
                        else:
                            self.selection = self.nearest_body(event.pos)
                    self.select_press = None
                elif self.drag_start is not None:
                    self.release(event.pos)

    # --- Simulation --------------------------------------------------------------------
    def update(self, frame_time):
        if self.rewinding:                      # hold Z: run the clock backwards
            self.rewind(REWIND_STEPS_PER_FRAME)
            if self.following:
                self.view.center = pygame.Vector2(self.target.pos)
            return
        advancing = not self.paused or self.step_request > 0
        if not self.paused:
            self.accumulator += (self.speed / FPS) if DETERMINISTIC else frame_time * self.speed
        elif self.step_request > 0:             # one frame's worth of sim time
            self.accumulator += self.speed / FPS
            self.step_request -= 1
        if advancing:
            steps = int(self.accumulator / PHYSICS_DT)
            self.accumulator -= steps * PHYSICS_DT
            if steps > MAX_STEPS_PER_FRAME:     # can't keep up: slow down, don't freeze
                steps, self.accumulator = MAX_STEPS_PER_FRAME, 0.0
            self.events = []
            for b in self.bodies:               # spacecraft engines for this frame
                if b.pilot is not None:
                    keys = self.keys_held if b is self.selection else set()
                    steer(b, self.bodies, steps * PHYSICS_DT, frame_time, keys)
            simulate(self.bodies, PHYSICS_DT, steps, self.mode, self.events, self.rng)
            if self.mode == "shatter":
                self.tidal_check()
            for kind, pos, strength, mass in self.events:
                self.flashes.add(kind, pos, strength)
                self.sound.play(kind, mass, strength)
            self.sim_time += steps * PHYSICS_DT
            self.history.record(self.sim_time, self.bodies, self.sun, self.target, self.rng)
            if self.show_energy:
                self.sample_energy()

        # Delete bodies far outside the view (farther when zoomed out)
        cull = max(CULL_DISTANCE, 2 * math.hypot(*self.screen.get_size()) / self.view.zoom)
        self.bodies = [b for b in self.bodies
                       if b.fixed or b is self.sun or b is self.target
                       or b.pos.distance_to(self.view.center) < cull]
        self.after_removals()
        self.n_particles = sum(1 for b in self.bodies if b.particle)
        if self.following:
            self.view.center = pygame.Vector2(self.target.pos)

        if self.show_trails and advancing:
            target, following = self.target, self.following
            crowded = self.crowded
            for b in self.bodies:
                if crowded and b.particle:
                    continue
                # While following, other trails are stored relative to the target
                # (so orbits draw as clean loops); the target's own trail stays in
                # world coordinates to show its path through space.
                if following and b is not target:
                    b.trail.append((b.pos.x - target.pos.x, b.pos.y - target.pos.y))
                else:
                    b.trail.append((b.pos.x, b.pos.y))

    # --- Drawing ---------------------------------------------------------------------
    def draw_selection(self, primary, el):
        """Highlight ring on the selected body plus its predicted Kepler orbit."""
        screen, view, sel = self.screen, self.view, self.selection
        if primary is not None and el is not None:
            base = primary.pos
            pts = [view.to_screen((base.x + x, base.y + y)) for x, y in orbit_points(el)]
            if len(pts) > 1:
                col = [int(c * 0.6) for c in (ui.ACCENT if el["bound"] else ui.BAD)]
                pygame.draw.lines(screen, col, el["bound"], [(p.x, p.y) for p in pts], 1)
            # periapsis / apoapsis markers
            w = el["omega"]
            for dist in (el["periapsis"], el["apoapsis"]):
                if dist is None:
                    continue
                ang = w if dist == el["periapsis"] else w + math.pi
                q = view.to_screen((base.x + dist * math.cos(ang), base.y + dist * math.sin(ang)))
                pygame.draw.circle(screen, ui.ACCENT, (round(q.x), round(q.y)), 3)
        p = view.to_screen(sel.pos)
        pulse = 2 * math.sin(pygame.time.get_ticks() / 250)
        r = max(sel.radius * view.zoom, 4) + 7 + pulse
        pygame.draw.circle(screen, ui.ACCENT, (round(p.x), round(p.y)), round(r), 2)

    def draw_orbit_ghost(self, mouse, r, color):
        """Orbit tool preview: the circle a click here would create."""
        view = self.view
        world = view.to_world(mouse)
        primary = strongest_pull_at(world, self.bodies)
        if primary is None:
            return
        c = view.to_screen(primary.pos)
        rad = c.distance_to(mouse)
        if rad < 2:
            return
        pygame.draw.circle(self.screen, [int(v * 0.5) for v in ui.GOOD],
                           (round(c.x), round(c.y)), round(rad), 1)
        pygame.draw.circle(self.screen, color, mouse, max(1, round(r * view.zoom)), 1)
        reverse = pygame.key.get_mods() & pygame.KMOD_SHIFT
        tangent = (pygame.Vector2(mouse) - c).rotate(90 if reverse else -90)
        tangent.scale_to_length(22)
        draw_arrow(self.screen, mouse, pygame.Vector2(mouse) + tangent, ui.GOOD)

    def draw(self):
        screen, view, sun, hud = self.screen, self.view, self.sun, self.hud
        mouse = pygame.Vector2(pygame.mouse.get_pos())
        following, target = self.following, self.target

        self.starfield.draw(screen, view)
        if self.show_field:
            self.field.draw(screen, self.bodies, view)
        crowded = self.crowded
        if self.show_trails:
            for b in self.bodies:
                if crowded and b.particle:
                    continue
                rel = following and b is not target
                b.draw_trail(screen, view, (target.pos.x, target.pos.y) if rel else (0.0, 0.0))
        dots = crowded and view.zoom < 2.5
        if dots:
            draw_points(screen, [b for b in self.bodies if b.particle], view)
        for b in self.bodies:
            if not (dots and b.particle):
                b.draw(screen, view)
        self.flashes.draw(screen, view)
        if self.show_lagrange and self.lagrange:
            pts = lagrange_points(*self.lagrange)
            hud.draw_lagrange(screen, {k: view.to_screen(p) for k, p in pts.items()})

        inspector = None
        if self.selection is not None:
            primary, el, inspector = self.selection_info()
            self.draw_selection(primary, el)

        name, m, r, color = self.preset_body()
        aim = None
        dragging = (self.drag_start is not None
                    and mouse.distance_to(self.drag_start) >= CLICK_SLOP)
        if dragging:
            vel = self.launch_velocity(mouse)
            start = view.to_world(self.drag_start)
            # Readout is relative to the followed body (e.g. a moon around a planet)
            ref = target if following else sun
            v_circ = orbit = None
            if ref in self.bodies:
                v_circ = circular_speed(ref.mass, start.distance_to(ref.pos))
                rel_vel = vel if following else vel - ref.vel
                orbit = orbit_info(start - ref.pos, rel_vel, ref.mass, ref.radius + r)
            status_color = hud.orbit_status(orbit)[1]
            if self.show_preview:
                dot = [int(c * 0.6) for c in status_color]
                v0 = vel + target.vel if following else vel
                for p in predict_path(self.bodies, tuple(start), tuple(v0),
                                      target if following else None, r):
                    q = view.to_screen((p[0], p[1]))
                    pygame.draw.circle(screen, dot, (round(q.x), round(q.y)), 1)
            Body(start, m, r, color).draw(screen, view)
            draw_arrow(screen, self.drag_start,
                       self.drag_start + vel * (view.zoom / LAUNCH_SCALE), status_color)
            aim = (mouse, vel.length(), v_circ, orbit)
        elif self.select_tool and not hud.blocked(mouse):
            # Select tool: crosshair, and ring the body a click would pick
            pygame.draw.line(screen, ui.DIM, (mouse.x - 6, mouse.y), (mouse.x + 6, mouse.y))
            pygame.draw.line(screen, ui.DIM, (mouse.x, mouse.y - 6), (mouse.x, mouse.y + 6))
            cand = self.nearest_body(mouse)
            if cand is not None and cand is not self.selection:
                p = view.to_screen(cand.pos)
                pygame.draw.circle(screen, [int(c * 0.7) for c in ui.ACCENT], (round(p.x), round(p.y)),
                                   round(max(cand.radius * view.zoom, 4) + 7), 1)
        elif self.drag_start is None and not hud.blocked(mouse):
            if self.body_at(mouse) is not None:         # hint: this body is clickable
                pygame.draw.circle(screen, ui.DIM, mouse, 3)
            elif self.orbit_tool:
                self.draw_orbit_ghost(mouse, r, color)
            else:
                pygame.draw.circle(screen, color, mouse, max(1, round(r * view.zoom)), 1)

        # --- UI ---
        hud.begin(mouse, self.slider[0] if self.slider else None)
        cam = f"FOLLOW {target.name.upper()}"[:18] if following else "FIXED"
        toggles = [
            ("M", "Collisions", self.mode.upper(), True, ("key", pygame.K_m)),
            ("L", "Trails", "ON" if self.show_trails else "OFF", self.show_trails,
             ("key", pygame.K_l)),
            ("T", "Aim preview", "ON" if self.show_preview else "OFF", self.show_preview,
             ("key", pygame.K_t)),
            ("V", "Camera", cam, following, ("key", pygame.K_v)),
            ("0", "Zoom", f"{view.zoom:.2f}x", abs(view.zoom - 1) > 1e-6, ("key", pygame.K_0)),
            (", .", "Speed", f"{self.speed:g}x", self.speed != 1, ("speed", None)),
            ("K", "Lagrange pts", "ON" if self.show_lagrange else "OFF", self.show_lagrange,
             ("key", pygame.K_k)),
            ("O", "Orbit tool", "ON" if self.orbit_tool else "OFF", self.orbit_tool,
             ("key", pygame.K_o)),
            ("W", "Gravity field", "ON" if self.show_field else "OFF", self.show_field,
             ("key", pygame.K_w)),
            ("E", "Energy graph", "ON" if self.show_energy else "OFF", self.show_energy,
             ("key", pygame.K_e)),
            ("X", "Sound", ("ON" if self.sound.enabled else "OFF") if self.sound.available
             else "N/A", self.sound.enabled, ("key", pygame.K_x)),
            ("Z", "Rewind", f"{self.history.seconds:.0f} s", self.history.seconds > 0,
             ("rewind", 25)),
            ("P", "Scene", (SCENARIOS[self.scenario_idx][0] if self.scenario_idx is not None
                            else "FROM FILE").upper()[:17], True, ("key", pygame.K_p)),
        ]
        status = hud.draw_status(screen, self.clock.get_fps(), len(self.bodies),
                                 self.sim_time, toggles)
        ti = self.sun_type_index()
        (mlo, mhi), (rlo, rhi) = SUN_MASS_RANGE, SUN_RADIUS_RANGE
        left = status.copy()
        left.union_ip(hud.draw_sun_panel(
            screen, status.bottom + 10, SUN_TYPES, ti,
            SUN_TYPES[ti][0] if ti is not None else "Custom",
            sun.mass, sun.radius,
            math.log(max(sun.mass, 1) / mlo) / math.log(mhi / mlo),
            (sun.radius - rlo) / (rhi - rlo),
            sun.fixed, sun.accent, compact=self.show_energy))
        if self.show_energy:
            left.union_ip(hud.draw_energy(screen, list(self.energy_log), *self.energy_scales))
        controls = hud.draw_controls(screen, compact=inspector is not None)
        if inspector is not None:
            hud.draw_inspector(screen, controls.bottom + 10, inspector)
        hud.draw_toolbar(screen, PRESETS, self.preset_idx, r, m, self.size_mult,
                         self.mass_mult, SIZE_RANGE, MASS_RANGE, self.select_tool, avoid=left)
        if hud.scenes_open:
            hud.draw_scenes(screen, [(n, d) for n, d, _ in SCENARIOS], self.scenario_idx)
        if self.rewinding:
            hud.draw_rewind(screen, self.sim_time, self.history.seconds)
        elif self.paused:
            hud.draw_paused(screen)
        if self.toast and pygame.time.get_ticks() < self.toast[1]:
            hud.draw_toast(screen, self.toast[0])
        if aim:                                   # on top of everything else
            hud.draw_aim(screen, *aim)
        pygame.display.flip()

    def run(self):
        while self.running:
            frame_time = min(self.clock.tick(FPS) / 1000, MAX_FRAME_TIME)
            self.handle_events()
            self.update(frame_time)
            self.draw()
        pygame.quit()


def main():
    App().run()
