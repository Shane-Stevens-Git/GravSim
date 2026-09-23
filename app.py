"""The GravSim application: state, input handling and drawing."""
import math
from collections import deque

import pygame

import ui
from body import Body, View
from config import *
from physics import circular_speed, orbit_info, predict_path, simulate
from render import draw_arrow, make_starfield
from scenes import make_scene


class App:
    """Owns the simulation state, input handling and drawing."""

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("GravSim")
        self.clock = pygame.time.Clock()
        self.hud = ui.HUD(WIDTH, HEIGHT)
        self.background = make_starfield()
        self.view = View()

        self.preset_idx = 2         # start on "Planet"
        self.size_mult = self.mass_mult = 1.0
        self.drag_start = None      # screen position of mouse-down while aiming
        self.slider = None          # (name, track rect) while dragging a slider
        self.show_preview = True
        self.show_trails = True
        self.follow = True          # camera keeps the sun centered
        self.mode = "merge"         # collision mode: "merge" or "bounce"
        self.paused = False
        self.running = True
        self.accumulator = 0.0
        self.sim_time = 0.0
        _name, *cfg = SUN_TYPES[DEFAULT_SUN]
        self.reset(tuple(cfg), fixed=False)

    # --- State helpers -----------------------------------------------------------
    @property
    def following(self):
        return self.follow and self.sun in self.bodies

    def set_sun(self, body):
        """Make `body` the main body (camera target, sun panel, HUD reference)."""
        self.sun = body
        body.trail = deque(maxlen=SUN_TRAIL_LENGTH)

    def reset(self, sun_cfg=None, fixed=None):
        """Restart the scene, keeping the current sun settings by default."""
        if sun_cfg is None:
            sun_cfg = (self.sun.mass, self.sun.radius, self.sun.color, self.sun.kind)
        if fixed is None:
            fixed = self.sun.fixed
        self.bodies = make_scene(sun_cfg, fixed)
        self.set_sun(self.bodies[0])
        self.view.center = pygame.Vector2(self.sun.pos)
        self.sim_time = 0.0

    def clear_trails(self):
        for b in self.bodies:
            b.trail.clear()

    def select_preset(self, i):
        self.preset_idx = i
        self.size_mult = self.mass_mult = 1.0

    def selected(self):
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
        # While following, the sun is locked to the center, so zoom about it.
        self.view.zoom_by(factor, None if self.following else screen_pos)

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
        if k == pygame.K_ESCAPE:
            self.running = False
        elif k == pygame.K_SPACE:
            self.paused = not self.paused
        elif k == pygame.K_h:
            self.hud.show_help = not self.hud.show_help
        elif k == pygame.K_s:
            self.hud.sun_collapsed = not self.hud.sun_collapsed
        elif k == pygame.K_t:
            self.show_preview = not self.show_preview
        elif k == pygame.K_l:
            self.show_trails = not self.show_trails
            self.clear_trails()
        elif k == pygame.K_m:
            self.mode = "bounce" if self.mode == "merge" else "merge"
        elif k == pygame.K_v:
            self.follow = not self.follow
            self.clear_trails()                 # old trails were in the old frame
        elif k == pygame.K_f:
            if self.sun in self.bodies:
                self.sun.fixed = not self.sun.fixed
                self.sun.vel.update(0, 0)
        elif k == pygame.K_c:
            self.bodies = [b for b in self.bodies if b is self.sun]
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
        elif kind == "sun_recenter":
            self.recenter()
        elif kind == "slider":
            self.slider = (arg, ref)
            self.update_slider(pos)

    def throw(self, pos):
        _, m, r, color = self.selected()
        vel = self.launch_velocity(pos)
        if self.following:                      # throw relative to the sun's motion
            vel += self.sun.vel
        self.bodies.append(Body(self.view.to_world(self.drag_start), m, r, color, vel=vel))
        self.drag_start = None

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self.handle_key(event.key)
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
                        self.drag_start = pygame.Vector2(event.pos)
                elif event.button == 3:
                    self.drag_start = None
            elif event.type == pygame.MOUSEMOTION:
                if self.slider:
                    self.update_slider(event.pos)
                elif event.buttons[1]:          # middle-drag pans the view
                    if self.follow:
                        self.follow = False
                        self.clear_trails()
                    self.view.center -= pygame.Vector2(event.rel) / self.view.zoom
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.slider:
                    self.slider = None
                elif self.drag_start is not None:
                    self.throw(event.pos)

    # --- Simulation --------------------------------------------------------------------
    def update(self, frame_time):
        if not self.paused:
            self.accumulator += frame_time
            steps = int(self.accumulator / PHYSICS_DT)
            self.accumulator -= steps * PHYSICS_DT
            simulate(self.bodies, PHYSICS_DT, steps, self.mode)
            self.sim_time += steps * PHYSICS_DT

        if self.sun not in self.bodies and self.bodies:   # sun swallowed or flung away
            self.set_sun(max(self.bodies, key=lambda b: b.mass))
        if self.following:
            self.view.center = pygame.Vector2(self.sun.pos)

        # Delete bodies far outside the view (farther when zoomed out)
        cull = max(CULL_DISTANCE, 2 * math.hypot(WIDTH, HEIGHT) / self.view.zoom)
        self.bodies = [b for b in self.bodies if b.fixed or b is self.sun
                       or b.pos.distance_to(self.view.center) < cull]

        if self.show_trails and not self.paused:
            sun, following = self.sun, self.following
            for b in self.bodies:
                # While following, other trails are stored relative to the sun (so
                # orbits draw as clean loops); the sun's own trail stays in world
                # coordinates to show its path through space.
                if following and b is not sun:
                    b.trail.append((b.pos.x - sun.pos.x, b.pos.y - sun.pos.y))
                else:
                    b.trail.append((b.pos.x, b.pos.y))

    # --- Drawing ---------------------------------------------------------------------
    def draw(self):
        screen, view, sun, hud = self.screen, self.view, self.sun, self.hud
        mouse = pygame.Vector2(pygame.mouse.get_pos())
        following = self.following

        screen.blit(self.background, (0, 0))
        if self.show_trails:
            for b in self.bodies:
                rel = following and b is not sun
                b.draw_trail(screen, view, (sun.pos.x, sun.pos.y) if rel else (0.0, 0.0))
        for b in self.bodies:
            b.draw(screen, view)

        name, m, r, color = self.selected()
        aim = None
        if self.drag_start is not None:
            vel = self.launch_velocity(mouse)
            start = view.to_world(self.drag_start)
            v_circ = orbit = None
            if sun in self.bodies:
                v_circ = circular_speed(sun.mass, start.distance_to(sun.pos))
                rel_vel = vel if following else vel - sun.vel
                orbit = orbit_info(start - sun.pos, rel_vel, sun.mass, sun.radius + r)
            status_color = hud.orbit_status(orbit)[1]
            if self.show_preview:
                dot = [int(c * 0.6) for c in status_color]
                v0 = vel + sun.vel if following else vel
                for p in predict_path(self.bodies, tuple(start), tuple(v0),
                                      sun if following else None, r):
                    q = view.to_screen((p[0], p[1]))
                    pygame.draw.circle(screen, dot, (round(q.x), round(q.y)), 1)
            Body(start, m, r, color).draw(screen, view)
            draw_arrow(screen, self.drag_start,
                       self.drag_start + vel * (view.zoom / LAUNCH_SCALE), status_color)
            aim = (mouse, vel.length(), v_circ, orbit)
        elif not hud.blocked(mouse):
            pygame.draw.circle(screen, color, mouse, max(1, round(r * view.zoom)), 1)

        # --- UI ---
        hud.begin(mouse, self.slider[0] if self.slider else None)
        toggles = [
            ("M", "Collisions", self.mode.upper(), True, ("key", pygame.K_m)),
            ("L", "Trails", "ON" if self.show_trails else "OFF", self.show_trails,
             ("key", pygame.K_l)),
            ("T", "Aim preview", "ON" if self.show_preview else "OFF", self.show_preview,
             ("key", pygame.K_t)),
            ("V", "Camera", "FOLLOW SUN" if following else "FIXED", following,
             ("key", pygame.K_v)),
            ("0", "Zoom", f"{view.zoom:.2f}x", abs(view.zoom - 1) > 1e-6, ("key", pygame.K_0)),
        ]
        status = hud.draw_status(screen, self.clock.get_fps(), len(self.bodies),
                                 self.sim_time, toggles)
        ti = self.sun_type_index()
        (mlo, mhi), (rlo, rhi) = SUN_MASS_RANGE, SUN_RADIUS_RANGE
        hud.draw_sun_panel(
            screen, status.bottom + 10, SUN_TYPES, ti,
            SUN_TYPES[ti][0] if ti is not None else "Custom",
            sun.mass, sun.radius,
            math.log(max(sun.mass, 1) / mlo) / math.log(mhi / mlo),
            (sun.radius - rlo) / (rhi - rlo),
            sun.fixed, sun.accent)
        hud.draw_controls(screen)
        hud.draw_toolbar(screen, PRESETS, self.preset_idx, r, m, self.size_mult,
                         self.mass_mult, SIZE_RANGE, MASS_RANGE)
        if self.paused:
            hud.draw_paused(screen)
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
