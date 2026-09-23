"""On-screen UI for GravSim: status panel, sun panel, controls panel, body
toolbar and the aiming readout.

The HUD only draws. While drawing it records clickable regions; main.py asks
`hit(pos)` which action (if any) a click lands on, and `blocked(pos)` whether
a click is over a panel (so it shouldn't start a throw).
"""
import math

import pygame

# --- Palette -------------------------------------------------------------------
TEXT = (222, 227, 240)
DIM = (122, 131, 156)
ACCENT = (120, 170, 255)
PANEL_BG = (14, 18, 32, 215)
PANEL_BG_HI = (30, 37, 62, 235)
PANEL_BORDER = (52, 62, 92)
HOVER_BG = (32, 40, 66)
KEY_BG = (36, 44, 70)
KEY_BORDER = (80, 92, 130)
TRACK = (40, 48, 74)
from config import BLACK_HOLE_RING

# Orbit-status colors used by the aim readout (and the aim arrow)
GOOD = (110, 220, 150)
INFO = (120, 170, 255)
WARN = (245, 185, 85)
BAD = (240, 100, 90)

PAD = 12

# Inspector color swatches
BODY_COLORS = [(255, 110, 110), (255, 160, 80), (255, 215, 90), (170, 230, 110),
               (90, 210, 140), (90, 210, 220), (100, 170, 255), (150, 130, 255),
               (210, 130, 255), (255, 130, 200), (235, 235, 245), (150, 155, 170)]
SIDE_W = 250        # width of the left-hand panels


class HUD:
    def __init__(self, width, height):
        self.w, self.h = width, height
        sans = "segoeui,helveticaneue,helvetica,arial"
        mono = "consolas,menlo,dejavusansmono,couriernew"
        self.f_title = pygame.font.SysFont(sans, 15, bold=True)
        self.f_label = pygame.font.SysFont(sans, 14)
        self.f_small = pygame.font.SysFont(sans, 11, bold=True)
        self.f_num = pygame.font.SysFont(mono, 14)
        self.f_big = pygame.font.SysFont(mono, 22, bold=True)
        self.show_help = True
        self.sun_collapsed = False
        self.scenes_open = False
        self.help_tab = 0
        self._panel_cache = {}
        self.regions = []       # (hit rect, action, reference rect)
        self.blockers = []      # panel rects that swallow clicks
        self.mouse = (0, 0)
        self.active_slider = None

    # --- Frame bookkeeping / hit testing ---------------------------------------------
    def begin(self, mouse, active_slider=None):
        self.mouse = (int(mouse[0]), int(mouse[1]))
        self.active_slider = active_slider
        self.regions = []
        self.blockers = []

    def add(self, rect, action, ref=None):
        self.regions.append((pygame.Rect(rect), action, pygame.Rect(ref or rect)))

    def hit(self, pos):
        """(action, reference rect) for the topmost region under pos, or None."""
        for rect, action, ref in reversed(self.regions):
            if rect.collidepoint(pos):
                return action, ref
        return None

    def blocked(self, pos):
        return any(r.collidepoint(pos) for r in self.blockers)

    def hovered(self, rect):
        return pygame.Rect(rect).collidepoint(self.mouse)

    # --- Primitives ------------------------------------------------------------
    def panel(self, surface, rect, bg=PANEL_BG, border=PANEL_BORDER, width=1, radius=10,
              block=True):
        rect = pygame.Rect(rect)
        key = (rect.size, bg, border, width, radius)
        s = self._panel_cache.get(key)
        if s is None:                   # translucent panels are cached by look
            if len(self._panel_cache) > 64:
                self._panel_cache.clear()
            s = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(s, bg, s.get_rect(), border_radius=radius)
            if border:
                pygame.draw.rect(s, border, s.get_rect(), width, border_radius=radius)
            self._panel_cache[key] = s
        surface.blit(s, rect.topleft)
        if block:
            self.blockers.append(rect)
        return rect

    def text(self, surface, font, txt, color, pos, anchor="topleft"):
        img = font.render(txt, True, color)
        rect = img.get_rect(**{anchor: pos})
        surface.blit(img, rect)
        return rect

    def keycap(self, surface, key, pos, min_w=20):
        """A small rounded key label, e.g. [M]. pos is its top-left corner."""
        img = self.f_small.render(key, True, TEXT)
        rect = pygame.Rect(pos, (max(min_w, img.get_width() + 10), 19))
        pygame.draw.rect(surface, KEY_BG, rect, border_radius=4)
        pygame.draw.rect(surface, KEY_BORDER, rect, 1, border_radius=4)
        surface.blit(img, img.get_rect(center=rect.center))
        return rect

    def bar(self, surface, rect, t, color):
        """Thin progress bar, t in 0..1."""
        rect = pygame.Rect(rect)
        pygame.draw.rect(surface, TRACK, rect, border_radius=2)
        fill = rect.copy()
        fill.width = max(2, round(rect.width * min(max(t, 0), 1)))
        pygame.draw.rect(surface, color, fill, border_radius=2)

    def slider(self, surface, track, t, color, name):
        """Draggable slider. Registers action ('slider', name)."""
        track = pygame.Rect(track)
        t = min(max(t, 0.0), 1.0)
        pygame.draw.rect(surface, TRACK, track, border_radius=3)
        fill = track.copy()
        fill.width = max(3, round(track.width * t))
        pygame.draw.rect(surface, color, fill, border_radius=3)
        hit = track.inflate(16, 20)
        hot = self.active_slider == name or hit.collidepoint(self.mouse)
        knob = (track.x + round(track.width * t), track.centery)
        pygame.draw.circle(surface, TEXT, knob, 8 if hot else 7)
        pygame.draw.circle(surface, color, knob, 8 if hot else 7, 2)
        self.add(hit, ("slider", name), track)

    def button(self, surface, rect, label, action, key=None, on=False, small=False):
        rect = pygame.Rect(rect)
        hov = self.hovered(rect)
        pygame.draw.rect(surface, HOVER_BG if hov or on else (22, 28, 48), rect, border_radius=6)
        pygame.draw.rect(surface, ACCENT if on else KEY_BORDER, rect, 1, border_radius=6)
        img = (self.f_small if small else self.f_label).render(label, True, ACCENT if on else TEXT)
        if key:
            kw = max(20, self.f_small.size(key)[0] + 10)     # keycap width
            x = rect.centerx - (kw + 6 + img.get_width()) // 2
            self.keycap(surface, key, (x, rect.centery - 9))
            surface.blit(img, (x + kw + 6, rect.centery - img.get_height() // 2))
        else:
            surface.blit(img, img.get_rect(center=rect.center))
        self.add(rect, action)

    @staticmethod
    def star_icon(surface, center, r, color, kind):
        if kind == "blackhole":
            pygame.draw.circle(surface, BLACK_HOLE_RING, center, r + 3, 2)
            pygame.draw.circle(surface, (0, 0, 0), center, r)
        else:
            pygame.draw.circle(surface, color, center, r)

    # --- Status panel (top-left) -------------------------------------------------
    def draw_status(self, surface, fps, n_bodies, sim_time, toggles):
        """toggles: list of (key, label, value_text, is_on, action). Rows are clickable."""
        row_h = 24
        rect = self.panel(surface, (PAD, PAD, SIDE_W, 78 + row_h * len(toggles)))
        x, y = rect.x + 14, rect.y + 12
        self.text(surface, self.f_title, "SIMULATION", ACCENT, (x, y))
        self.text(surface, self.f_num, f"{fps:3.0f} fps", DIM, (rect.right - 14, y + 1), "topright")

        y += 28
        self.text(surface, self.f_label, "Bodies", DIM, (x, y))
        self.text(surface, self.f_num, f"{n_bodies}", TEXT, (x + 52, y + 1))
        self.text(surface, self.f_label, "Time", DIM, (x + 112, y))
        self.text(surface, self.f_num, f"{sim_time:6.1f} s", TEXT, (x + 152, y + 1))

        y += 26
        pygame.draw.line(surface, PANEL_BORDER, (rect.x + 10, y - 6), (rect.right - 10, y - 6))
        for key, label, value, on, action in toggles:
            row = pygame.Rect(rect.x + 6, y - 3, rect.width - 12, row_h - 1)
            if self.hovered(row):
                pygame.draw.rect(surface, HOVER_BG, row, border_radius=5)
            self.add(row, action)
            self.keycap(surface, key, (x, y))
            self.text(surface, self.f_label, label, TEXT, (x + 38, y + 1))
            self.text(surface, self.f_small, value, ACCENT if on else DIM,
                      (rect.right - 14, y + 3), "topright")
            y += row_h
        return rect

    # --- Sun panel (left, under the status panel) ------------------------------------
    def draw_sun_panel(self, surface, y, sun_types, type_idx, type_name, mass, radius,
                       mass_t, radius_t, pinned, color, compact=False):
        header_h = 36
        collapsed = self.sun_collapsed or compact
        if collapsed:
            rect = self.panel(surface, (PAD, y, SIDE_W, header_h))
        else:
            rect = self.panel(surface, (PAD, y, SIDE_W, 250))
        x = rect.x + 14

        header = pygame.Rect(rect.x, rect.y, rect.width, header_h)
        if self.hovered(header):
            pygame.draw.rect(surface, HOVER_BG, header.inflate(-8, -8), border_radius=6)
        self.text(surface, self.f_title, "SUN", ACCENT, (x, rect.y + 10))
        hint = self.text(surface, self.f_label, "show" if collapsed else "hide", DIM,
                         (rect.right - 14, rect.y + 10), "topright")
        self.keycap(surface, "S", (hint.x - 26, rect.y + 9))
        self.add(header, ("key", pygame.K_s))
        if collapsed:
            return rect

        # Star-type swatches
        cy = rect.y + header_h + 4
        sw, n = 40, len(sun_types)
        gap = (rect.width - 28 - n * sw) // max(1, n - 1)
        for i, (_name, _m, r, c, kind) in enumerate(sun_types):
            cell = pygame.Rect(x + i * (sw + gap), cy, sw, 40)
            sel, hov = i == type_idx, self.hovered(cell)
            pygame.draw.rect(surface, HOVER_BG if (sel or hov) else (22, 28, 48), cell, border_radius=6)
            if sel:
                pygame.draw.rect(surface, BLACK_HOLE_RING if kind == "blackhole" else c,
                                 cell, 2, border_radius=6)
            self.star_icon(surface, cell.center, max(4, min(12, round(r / 3.5))), c, kind)
            self.add(cell, ("sun_type", i))
        cy += 48
        self.text(surface, self.f_label, "Type", DIM, (x, cy))
        self.text(surface, self.f_label, type_name, TEXT, (rect.right - 14, cy), "topright")

        # Sliders
        cy += 28
        for label, value, t, name in (("Mass", f"{mass:,.0f}", mass_t, "sun_mass"),
                                      ("Radius", f"{radius}", radius_t, "sun_radius")):
            self.text(surface, self.f_label, label, DIM, (x, cy))
            self.text(surface, self.f_num, value, TEXT, (rect.right - 14, cy + 1), "topright")
            self.slider(surface, (x + 4, cy + 25, rect.width - 36, 6), t, color, name)
            cy += 46

        # Buttons
        cy += 2
        bw = (rect.width - 28 - 10) // 2
        self.button(surface, (x, cy, bw, 28), "Pinned" if pinned else "Free",
                    ("key", pygame.K_f), key="F", on=pinned)
        self.button(surface, (x + bw + 10, cy, bw, 28), "Recenter", ("sun_recenter", None))
        return rect

    # --- Controls panel (top-right) -----------------------------------------------
    # Controls legend, one tab per topic (Tab key or click to switch)
    CONTROL_TABS = [
        ("Bodies", [
            ("Drag", "Throw a body"),
            ("RMB", "Cancel a throw"),
            ("1-6 / click", "Choose body type"),
            ("Scroll", "Resize (keeps density)"),
            ("Shift+Scroll", "Change mass only"),
            ("O", "Orbit tool (click = orbit)"),
            ("Click body", "Select / inspect it"),
            ("Q", "Select tool (no throwing)"),
            ("[  /  ]", "Selected: less / more mass"),
            ("Del", "Delete selected"),
            ("B", "Ring around selected"),
            ("C", "Clear thrown bodies"),
        ]),
        ("View", [
            ("Ctrl+Scroll", "Zoom (also + / -)"),
            ("0", "Reset zoom"),
            ("Middle-drag", "Pan the view"),
            ("V", "Camera mode"),
            ("G", "Camera follows selected"),
            ("F11", "Fullscreen"),
            ("L", "Trails"),
            ("T", "Aim preview"),
            ("W", "Gravity field overlay"),
            ("A", "All predicted orbits"),
            ("K", "Lagrange points"),
            ("E", "Energy & momentum graph"),
            ("S", "Sun panel"),
        ]),
        ("Sim", [
            ("Space", "Pause / resume"),
            ("N", "Step one frame"),
            (", / .", "Slower / faster"),
            ("Z (hold)", "Rewind"),
            ("M", "Merge / shatter / bounce"),
            ("P", "Scenes menu"),
            ("R", "Reset scene"),
            ("Ctrl+S / O", "Save / load scene"),
            ("F5 / F9", "Quick save / load"),
            ("X", "Sound on / off"),
            ("H", "Hide this panel"),
            ("Esc", "Quit"),
        ]),
        ("Craft", [
            ("6", "Spacecraft body type"),
            ("Hold", "Keep station (L-point/orbit)"),
            ("Transfer", "Click a planet: fly there"),
            ("Follow", "Click a body: rendezvous"),
            ("Manual", "Fly it yourself:"),
            ("Up / Down", "Thrust / brake"),
            ("Left / Right", "Turn"),
            ("Off", "Engine off, coast"),
        ]),
    ]

    def draw_controls(self, surface, compact=False, settings_rows=()):
        """Controls legend with tabs, or just an 'H Controls' button when hidden
        (or when `compact`, e.g. while the inspector needs the space)."""
        if compact or not self.show_help:
            label = self.f_label.render("Controls", True, DIM)
            box = pygame.Rect(self.w - PAD - label.get_width() - 58, PAD, label.get_width() + 58, 34)
            rect = self.panel(surface, box, bg=PANEL_BG_HI if self.hovered(box) else PANEL_BG)
            self.keycap(surface, "H", (rect.x + 12, rect.y + 8))
            surface.blit(label, (rect.x + 42, rect.y + 8))
            self.add(rect, ("key", pygame.K_h))
            return rect
        row_h, key_w, w = 22, 100, 290
        tabs = [name for name, _ in self.CONTROL_TABS] + ["Physics"]
        self.help_tab %= len(tabs)
        longest = max(len(r) for _, r in self.CONTROL_TABS)     # fixed height per panel
        body_h = max(row_h * longest, 34 * len(settings_rows) + 40)
        rect = self.panel(surface, (self.w - PAD - w, PAD, w, 86 + body_h))
        x, y = rect.x + 14, rect.y + 12
        title = self.text(surface, self.f_title, "CONTROLS", ACCENT, (x, y))
        self.text(surface, self.f_small, "Tab: next tab", DIM, (title.right + 10, y + 3))
        hide = self.text(surface, self.f_label, "hide", DIM, (rect.right - 14, y + 1), "topright")
        cap = self.keycap(surface, "H", (hide.x - 26, y))
        self.add(cap.union(hide).inflate(8, 8), ("key", pygame.K_h))
        y += 28
        tab_w = (w - 28 - (len(tabs) - 1) * 4) // len(tabs)
        for i, name in enumerate(tabs):
            self.button(surface, (x + i * (tab_w + 4), y, tab_w, 24), name, ("help_tab", i),
                        on=i == self.help_tab, small=True)
        y += 36
        if self.help_tab == len(self.CONTROL_TABS):      # Physics: live settings
            for key, label, value, t, changed in settings_rows:
                self.text(surface, self.f_label, label, TEXT if changed else DIM, (x, y))
                self.text(surface, self.f_num, value, ACCENT if changed else TEXT,
                          (rect.right - 14, y + 1), "topright")
                self.slider(surface, (x + 4, y + 22, w - 36, 5), t, ACCENT, "set:" + key)
                y += 34
            self.button(surface, (x, y + 4, w - 28, 26), "Reset to defaults",
                        ("settings_defaults", None))
            return rect
        for key, desc in self.CONTROL_TABS[self.help_tab][1]:
            self.keycap(surface, key, (x, y))
            self.text(surface, self.f_label, desc, TEXT, (x + key_w, y + 1))
            y += row_h
        return rect

    # --- Inspector (right, under the controls panel) ---------------------------------
    def draw_inspector(self, surface, y, info):
        """Details for the selected body. info: name, color, accent, kind, mass,
        primary (name or None), speed, dist, el (orbital elements or None), following."""
        w = 320
        craft = info.get("craft")
        rect = self.panel(surface, (self.w - PAD - w, y, w, 298 + (112 if craft else 0)))
        x, ty = rect.x + 14, rect.y + 12

        self.star_icon(surface, (x + 6, ty + 9), 6, info["color"], info["kind"])
        self.text(surface, self.f_title, info["name"].upper(), info["accent"], (x + 20, ty))
        close = pygame.Rect(rect.right - 34, rect.y + 8, 24, 24)
        if self.hovered(close):
            pygame.draw.rect(surface, HOVER_BG, close, border_radius=5)
        c = close.center
        pygame.draw.line(surface, DIM, (c[0] - 5, c[1] - 5), (c[0] + 5, c[1] + 5), 2)
        pygame.draw.line(surface, DIM, (c[0] - 5, c[1] + 5), (c[0] + 5, c[1] - 5), 2)
        self.add(close, ("sel_close", None))

        ty += 30
        self.text(surface, self.f_label, "Orbiting", DIM, (x, ty))
        self.text(surface, self.f_label, info["primary"] or "nothing heavier", TEXT,
                  (rect.right - 14, ty), "topright")

        el = info["el"]
        cells = [("Speed", f"{info['speed']:.0f} px/s"),
                 ("Distance", f"{info['dist']:.0f} px" if info["dist"] is not None else "-")]
        if el:
            cells += [("Eccentricity", f"{el['e']:.3f}"),
                      ("Period", f"{el['period']:.1f} s" if el["bound"] else "-"),
                      ("Periapsis", f"{el['periapsis']:.0f} px"),
                      ("Apoapsis", f"{el['apoapsis']:.0f} px" if el["bound"] else "-")]
        ty += 26
        col_w = (w - 28) // 2
        for i, (label, value) in enumerate(cells):
            cx, cy = x + (i % 2) * col_w, ty + (i // 2) * 36
            self.text(surface, self.f_small, label.upper(), DIM, (cx, cy))
            self.text(surface, self.f_num, value, TEXT, (cx, cy + 14))
        ty += 3 * 36

        if el:
            if not el["bound"]:
                label, color = "Escape trajectory", BAD
            elif el["e"] < 0.1:
                label, color = "Near-circular orbit", GOOD
            else:
                label, color = "Elliptical orbit", INFO
            pygame.draw.circle(surface, color, (x + 4, ty + 9), 4)
            self.text(surface, self.f_label, label, color, (x + 14, ty))
        ty += 28

        self.text(surface, self.f_label, "Mass", DIM, (x, ty + 3))
        self.text(surface, self.f_num, f"{info['mass']:.4g}", TEXT, (x + 52, ty + 4))
        self.button(surface, (rect.right - 14 - 62, ty, 28, 24), "-", ("sel_mass", 1 / 1.5))
        self.button(surface, (rect.right - 14 - 28, ty, 28, 24), "+", ("sel_mass", 1.5))
        ty += 32

        # Color swatches (for a black hole these recolor its glowing ring)
        self.text(surface, self.f_label, "Color", DIM, (x, ty + 3))
        sx = x + 52
        step = (rect.right - 14 - sx - 9) / (len(BODY_COLORS) - 1)
        for i, col in enumerate(BODY_COLORS):
            c = (round(sx + i * step), ty + 11)
            hit = pygame.Rect(c[0] - 10, c[1] - 11, 20, 22)
            current = tuple(col) == tuple(info["accent"])
            if self.hovered(hit) or current:
                pygame.draw.circle(surface, TEXT if current else DIM, c, 11, 2)
            pygame.draw.circle(surface, col, c, 8)
            self.add(hit, ("sel_color", col))
        ty += 32

        bw = (w - 28 - 16) // 3
        self.button(surface, (x, ty, bw, 28), "Unfollow" if info["following"] else "Follow",
                    ("sel_follow", None), key="G", on=info["following"])
        self.button(surface, (x + bw + 8, ty, bw, 28), "Ring", ("sel_ring", None), key="B")
        self.button(surface, (x + 2 * (bw + 8), ty, bw, 28), "Delete", ("sel_delete", None),
                    key="Del")
        if craft:
            self.draw_autopilot(surface, x, ty + 40, w - 28, craft)
        return rect

    def draw_autopilot(self, surface, x, y, width, craft):
        """Spacecraft section: mode buttons, delta-v used, status line."""
        pygame.draw.line(surface, PANEL_BORDER, (x - 4, y - 6), (x + width + 4, y - 6))
        self.text(surface, self.f_small, "AUTOPILOT", DIM, (x, y))
        self.text(surface, self.f_small, f"dv used  {craft['dv']:,.0f} px/s", DIM,
                  (x + width, y), "topright")
        y += 18
        labels = [("off", "Off"), ("hold", "Hold"), ("transfer", "Transfer"),
                  ("follow", "Follow"), ("manual", "Manual")]
        bw = (width - 4 * 5) // 5
        for i, (mode, label) in enumerate(labels):
            self.button(surface, (x + i * (bw + 5), y, bw, 26), label, ("pilot", mode),
                        on=craft["mode"] == mode or craft.get("picking") == mode, small=True)
        y += 34
        color = WARN if craft.get("picking") else TEXT
        for line in self._wrap(craft["status"], self.f_label, width)[:2]:
            self.text(surface, self.f_label, line, color, (x, y))
            y += 18

    @staticmethod
    def _wrap(text, font, width):
        words, lines, cur = text.split(), [], ""
        for w in words:
            test = f"{cur} {w}".strip()
            if font.size(test)[0] <= width or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    # --- Scenes menu (modal) -------------------------------------------------------------
    def draw_scenes(self, surface, scenarios, current_idx):
        """scenarios: list of (name, description). Rows click to ('scene', i)."""
        # Dim the whole screen; clicking outside the menu closes it.
        full = pygame.Rect(0, 0, self.w, self.h)
        self.panel(surface, full, bg=(0, 0, 0, 140), border=None, radius=0)
        self.add(full, ("key", pygame.K_p))
        row_h, w = 54, 560
        h = 58 + row_h * len(scenarios) + 60
        rect = self.panel(surface, ((self.w - w) // 2, (self.h - h) // 2, w, h), bg=(14, 18, 32, 250))
        self.add(rect, ("noop", None))                  # clicks inside don't close it
        x, y = rect.x + 18, rect.y + 16
        self.text(surface, self.f_title, "SCENES", ACCENT, (x, y))
        hint = self.text(surface, self.f_label, "close", DIM, (rect.right - 18, y + 1), "topright")
        cap = self.keycap(surface, "P", (hint.x - 26, y))
        self.add(cap.union(hint).inflate(8, 8), ("key", pygame.K_p))
        y += 36
        for i, (name, desc) in enumerate(scenarios):
            row = pygame.Rect(rect.x + 8, y, w - 16, row_h - 4)
            cur = i == current_idx
            if self.hovered(row) or cur:
                pygame.draw.rect(surface, HOVER_BG, row, border_radius=8)
            if cur:
                pygame.draw.rect(surface, ACCENT, row, 1, border_radius=8)
            self.keycap(surface, str(i + 1), (x, y + 15))
            self.text(surface, self.f_title, name, TEXT, (x + 34, y + 6))
            self.text(surface, self.f_label, desc, DIM, (x + 34, y + 26))
            if cur:
                self.text(surface, self.f_small, "LOADED", ACCENT, (row.right - 12, y + 8), "topright")
            self.add(row, ("scene", i))
            y += row_h
        y += 8
        bw = (w - 36 - 12) // 2
        self.button(surface, (x, y, bw, 32), "Save scene...", ("save", None), key="Ctrl+S")
        self.button(surface, (x + bw + 12, y, bw, 32), "Load scene...", ("load", None), key="Ctrl+O")
        return rect

    def draw_toast(self, surface, text):
        img = self.f_label.render(text, True, TEXT)
        w = img.get_width() + 32
        rect = self.panel(surface, ((self.w - w) // 2, self.h - PAD - 80 - 12 - 34, w, 34),
                          border=ACCENT, block=False)
        surface.blit(img, img.get_rect(center=rect.center))

    def draw_lagrange(self, surface, points):
        """points: {label: screen Vector2}. Small diamonds with labels."""
        for label, p in points.items():
            x, y = round(p.x), round(p.y)
            color = GOOD if label in ("L4", "L5") else WARN      # stable vs unstable
            pygame.draw.polygon(surface, color, [(x, y - 6), (x + 6, y), (x, y + 6), (x - 6, y)], 1)
            self.text(surface, self.f_small, label, color, (x + 9, y - 16))

    # --- Body toolbar (bottom-center) -------------------------------------------------
    def draw_toolbar(self, surface, presets, selected_idx, radius, mass, size_mult, mass_mult,
                     size_range, mass_range, select_on=False, avoid=None):
        """`avoid`: rect of the left-hand panels. If they reach down into the
        toolbar's row (small windows), the toolbar starts to their right and
        its cards narrow to fit."""
        card_w, card_h, gap, info_w = 92, 80, 8, 230
        n = len(presets) + 1
        y = self.h - PAD - card_h
        x = (self.w - (n * (card_w + gap) + info_w)) // 2
        if avoid is not None and avoid.bottom > y - 8 and x < avoid.right + 10:
            x = avoid.right + 10
            card_w = max(60, min(card_w, (self.w - PAD - x - info_w) // n - gap))

        # Select tool card: clicks pick bodies, never create them
        hov = self.hovered((x, y, card_w, card_h))
        rect = self.panel(surface, (x, y, card_w, card_h),
                          bg=PANEL_BG_HI if (select_on or hov) else PANEL_BG,
                          border=ACCENT if select_on else (KEY_BORDER if hov else PANEL_BORDER),
                          width=2 if select_on else 1)
        self.keycap(surface, "Q", (rect.x + 6, rect.y + 6))
        cx, cy = rect.centerx - 4, rect.y + 24                  # mouse-pointer icon
        pygame.draw.polygon(surface, ACCENT if select_on else TEXT,
                            [(cx, cy), (cx, cy + 20), (cx + 5, cy + 15), (cx + 9, cy + 23),
                             (cx + 12, cy + 21), (cx + 8, cy + 14), (cx + 14, cy + 14)])
        self.text(surface, self.f_label, "Select", TEXT if (select_on or hov) else DIM,
                  (rect.centerx, rect.bottom - 8), "midbottom")
        self.add(rect, ("select_tool", None))
        x += card_w + gap

        for i, (name, _m, r, color) in enumerate(presets):
            sel = i == selected_idx and not select_on
            hov = self.hovered((x, y, card_w, card_h))
            rect = self.panel(surface, (x, y, card_w, card_h),
                              bg=PANEL_BG_HI if (sel or hov) else PANEL_BG,
                              border=color if sel else (KEY_BORDER if hov else PANEL_BORDER),
                              width=2 if sel else 1)
            self.keycap(surface, str(i + 1), (rect.x + 6, rect.y + 6))
            if name == "Spacecraft":                     # arrowhead icon
                cx, cy = rect.centerx, rect.y + 34
                pygame.draw.polygon(surface, color, [(cx + 11, cy), (cx - 8, cy - 8),
                                                     (cx - 4, cy), (cx - 8, cy + 8)])
            else:
                pygame.draw.circle(surface, color, (rect.centerx, rect.y + 34), min(r, 16))
            self.text(surface, self.f_label, name, TEXT if (sel or hov) else DIM,
                      (rect.centerx, rect.bottom - 8), "midbottom")
            self.add(rect, ("preset", i))
            x += card_w + gap

        rect = self.panel(surface, (x, y, info_w, card_h))
        ix, iy = rect.x + 14, rect.y + 9
        if select_on:
            self.text(surface, self.f_title, "Select tool", ACCENT, (ix, iy))
            self.text(surface, self.f_label, "Click near a body to select it", DIM, (ix, iy + 24))
            self.text(surface, self.f_label, "Drag to pan  -  1-6 to throw again", DIM, (ix, iy + 44))
            return
        name, _m, _r, color = presets[selected_idx]
        self.text(surface, self.f_title, name, color, (ix, iy))
        rows = (("Radius", f"{radius}", size_mult, size_range),
                ("Mass", f"{mass:.4g}", mass_mult, mass_range))
        for j, (label, value, mult, (lo, hi)) in enumerate(rows):
            ry = iy + 24 + j * 22
            self.text(surface, self.f_label, label, DIM, (ix, ry))
            self.text(surface, self.f_num, value, TEXT, (ix + 52, ry + 1))
            t = (math.log(mult) - math.log(lo)) / (math.log(hi) - math.log(lo))
            self.bar(surface, (rect.right - 104, ry + 8, 50, 4), t, color)
            self.text(surface, self.f_small, f"x{mult:.2f}", DIM, (rect.right - 10, ry + 2), "topright")

    # --- Aim readout (follows the cursor while dragging) -------------------------------
    @staticmethod
    def orbit_status(orbit):
        """orbit: None or dict(e=, impact=, escape=) -> (label, color)."""
        if orbit is None:
            return "", INFO
        if orbit["escape"]:
            return "Escape trajectory", BAD
        if orbit["impact"]:
            return "Impact course", WARN
        if orbit["e"] < 0.1:
            return "Near-circular orbit", GOOD
        return "Elliptical orbit", INFO

    def draw_aim(self, surface, mouse, speed, v_circ, orbit):
        label, color = self.orbit_status(orbit)
        lines = 1 + (v_circ is not None) + bool(label)
        w, h = 200, 16 + 30 + 20 * (lines - 1)
        x = min(mouse[0] + 20, self.w - w - PAD)
        y = min(mouse[1] + 20, self.h - h - PAD - 90)
        rect = self.panel(surface, (x, y, w, h), bg=(14, 18, 32, 250),
                          border=color if label else PANEL_BORDER, block=False)
        tx, ty = rect.x + 12, rect.y + 8
        spd = self.text(surface, self.f_big, f"{speed:.0f}", TEXT, (tx, ty))
        self.text(surface, self.f_label, "px/s", DIM, (spd.right + 6, spd.bottom - 18))
        ty += 32
        if v_circ is not None:
            self.text(surface, self.f_label, f"{speed / v_circ:.2f}x circular speed", DIM, (tx, ty))
            ty += 20
        if label:
            pygame.draw.circle(surface, color, (tx + 4, ty + 9), 4)
            txt = label if orbit["escape"] or orbit["impact"] else f"{label}  e={orbit['e']:.2f}"
            self.text(surface, self.f_label, txt, color, (tx + 14, ty))
        return color

    # --- Energy & momentum graph (bottom-left) -----------------------------------------
    def sparkline(self, surface, rect, times, values, min_span):
        """One small line chart: thin line, faint midline, hover crosshair.
        Returns the index of the hovered sample, or None."""
        rect = pygame.Rect(rect)
        pygame.draw.line(surface, (34, 42, 66), (rect.x, rect.centery), (rect.right, rect.centery))
        if len(values) < 2:
            return None
        lo, hi = min(values), max(values)
        mid, span = (lo + hi) / 2, max(hi - lo, min_span)
        lo, hi = mid - span * 0.6, mid + span * 0.6
        t0, t1 = times[0], max(times[-1], times[0] + 1e-9)

        def pt(t, v):
            return (rect.x + (t - t0) / (t1 - t0) * rect.width,
                    rect.bottom - (v - lo) / (hi - lo) * rect.height)

        pygame.draw.lines(surface, ACCENT, False, [pt(t, v) for t, v in zip(times, values)], 2)
        if rect.inflate(0, 10).collidepoint(self.mouse):       # hover readout
            frac = (self.mouse[0] - rect.x) / rect.width
            i = min(range(len(times)), key=lambda k: abs(times[k] - (t0 + frac * (t1 - t0))))
            x, y = pt(times[i], values[i])
            pygame.draw.line(surface, DIM, (x, rect.y), (x, rect.bottom))
            pygame.draw.circle(surface, TEXT, (round(x), round(y)), 4)
            pygame.draw.circle(surface, ACCENT, (round(x), round(y)), 4, 2)
            return i
        return None

    def draw_energy(self, surface, log, energy_scale, momentum_scale):
        """log: list of (t, E, |p|). Two separate charts - different units,
        so never one chart with two y-axes."""
        w, h = SIDE_W, 206
        rect = self.panel(surface, (PAD, self.h - PAD - h, w, h))
        x, y = rect.x + 14, rect.y + 12
        self.text(surface, self.f_title, "ENERGY", ACCENT, (x, y))
        hide = self.text(surface, self.f_label, "hide", DIM, (rect.right - 14, y + 1), "topright")
        cap = self.keycap(surface, "E", (hide.x - 26, y))
        self.add(cap.union(hide).inflate(8, 8), ("key", pygame.K_e))
        times = [s[0] for s in log]
        energies = [s[1] for s in log]
        moms = [s[2] for s in log]
        e0 = energies[0] if energies else 0.0
        drift = (energies[-1] - e0) / abs(e0) * 100 if energies and e0 else 0.0

        def sci(v):
            return f"{v:.3g}" if abs(v) < 1e5 else f"{v:.2e}"

        # Charts first (they report the hovered sample), then the labels,
        # which show the hovered value instead of the latest one.
        y += 30
        hi_e = self.sparkline(surface, (x, y + 38, w - 28, 34), times, energies,
                              energy_scale * 1e-3)
        hi_p = self.sparkline(surface, (x, y + 108, w - 28, 34), times, moms,
                              momentum_scale * 1e-3 + 1e-6)
        hover = hi_e if hi_e is not None else hi_p
        k = hover if hover is not None else len(times) - 1
        self.text(surface, self.f_label, "Total energy", DIM, (x, y))
        self.text(surface, self.f_num, sci(energies[k]) if energies else "-", TEXT,
                  (rect.right - 14, y + 1), "topright")
        note = (f"at t = {times[k]:.1f} s" if hover is not None
                else f"change over window {drift:+.4f}%")
        self.text(surface, self.f_small, note, DIM, (x, y + 18))
        y += 84
        self.text(surface, self.f_label, "Momentum |p|", DIM, (x, y))
        self.text(surface, self.f_num, sci(moms[k]) if moms else "-", TEXT,
                  (rect.right - 14, y + 1), "topright")
        return rect

    def draw_rewind(self, surface, sim_time, seconds_left):
        img = self.f_title.render("REWINDING", True, TEXT)
        hint = self.f_num.render(f"t = {sim_time:.1f} s", True, DIM)
        w = img.get_width() + hint.get_width() + 140
        rect = self.panel(surface, ((self.w - w) // 2, PAD, w, 34), border=WARN, block=False)
        # little "<<" icon
        x, cy = rect.x + 14, rect.centery
        for dx in (0, 8):
            pygame.draw.polygon(surface, WARN, [(x + dx + 8, cy - 6), (x + dx, cy), (x + dx + 8, cy + 6)])
        surface.blit(img, (x + 24, rect.y + 8))
        surface.blit(hint, (x + 34 + img.get_width(), rect.y + 9))
        self.bar(surface, (rect.right - 76, cy - 2, 62, 4), seconds_left / 60, WARN)

    def draw_paused(self, surface):
        img = self.f_title.render("PAUSED", True, TEXT)
        hint = self.f_label.render("Space to resume  ·  N to step", True, DIM)
        w = img.get_width() + hint.get_width() + 40
        rect = self.panel(surface, ((self.w - w) // 2, PAD, w, 34), border=ACCENT, block=False)
        surface.blit(img, (rect.x + 14, rect.y + 8))
        surface.blit(hint, (rect.x + 26 + img.get_width(), rect.y + 9))
