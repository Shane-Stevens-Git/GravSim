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

    def button(self, surface, rect, label, action, key=None, on=False):
        rect = pygame.Rect(rect)
        hov = self.hovered(rect)
        pygame.draw.rect(surface, HOVER_BG if hov else (22, 28, 48), rect, border_radius=6)
        pygame.draw.rect(surface, ACCENT if on else KEY_BORDER, rect, 1, border_radius=6)
        img = self.f_label.render(label, True, TEXT)
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
                       mass_t, radius_t, pinned, color):
        header_h = 36
        if self.sun_collapsed:
            rect = self.panel(surface, (PAD, y, SIDE_W, header_h))
        else:
            rect = self.panel(surface, (PAD, y, SIDE_W, 250))
        x = rect.x + 14

        header = pygame.Rect(rect.x, rect.y, rect.width, header_h)
        if self.hovered(header):
            pygame.draw.rect(surface, HOVER_BG, header.inflate(-8, -8), border_radius=6)
        self.text(surface, self.f_title, "SUN", ACCENT, (x, rect.y + 10))
        hint = self.text(surface, self.f_label, "show" if self.sun_collapsed else "hide", DIM,
                         (rect.right - 14, rect.y + 10), "topright")
        self.keycap(surface, "S", (hint.x - 26, rect.y + 9))
        self.add(header, ("key", pygame.K_s))
        if self.sun_collapsed:
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
    CONTROLS = [
        ("Drag", "Throw a body"),
        ("RMB", "Cancel throw"),
        ("1-5 / click", "Choose body type"),
        ("Scroll", "Resize (keeps density)"),
        ("Shift+Scroll", "Change mass only"),
        ("Ctrl+Scroll", "Zoom (also + / -)"),
        ("Middle-drag", "Pan the view"),
        ("S", "Sun panel"),
        ("Space", "Pause / resume"),
        ("N", "Step one frame"),
        (", / .", "Slower / faster"),
        ("C", "Clear thrown bodies"),
        ("R", "Reset scene"),
        ("Esc", "Quit"),
    ]

    def draw_controls(self, surface):
        if not self.show_help:
            label = self.f_label.render("Controls", True, DIM)
            rect = self.panel(surface, (self.w - PAD - label.get_width() - 58, PAD,
                                        label.get_width() + 58, 34),
                              bg=PANEL_BG_HI if self.hovered(
                                  (self.w - PAD - label.get_width() - 58, PAD,
                                   label.get_width() + 58, 34)) else PANEL_BG)
            self.keycap(surface, "H", (rect.x + 12, rect.y + 8))
            surface.blit(label, (rect.x + 42, rect.y + 8))
            self.add(rect, ("key", pygame.K_h))
            return
        row_h, key_w = 24, 100
        rect = self.panel(surface, (self.w - PAD - 280, PAD, 280, 50 + row_h * len(self.CONTROLS)))
        x, y = rect.x + 14, rect.y + 12
        self.text(surface, self.f_title, "CONTROLS", ACCENT, (x, y))
        hide = self.text(surface, self.f_label, "hide", DIM, (rect.right - 14, y + 1), "topright")
        cap = self.keycap(surface, "H", (hide.x - 26, y))
        self.add(cap.union(hide).inflate(8, 8), ("key", pygame.K_h))
        y += 30
        for key, desc in self.CONTROLS:
            self.keycap(surface, key, (x, y))
            self.text(surface, self.f_label, desc, TEXT, (x + key_w, y + 1))
            y += row_h

    # --- Body toolbar (bottom-center) -------------------------------------------------
    def draw_toolbar(self, surface, presets, selected_idx, radius, mass, size_mult, mass_mult,
                     size_range, mass_range):
        card_w, card_h, gap, info_w = 92, 80, 8, 230
        total = len(presets) * (card_w + gap) + info_w
        x = (self.w - total) // 2
        y = self.h - PAD - card_h

        for i, (name, _m, r, color) in enumerate(presets):
            sel = i == selected_idx
            hov = self.hovered((x, y, card_w, card_h))
            rect = self.panel(surface, (x, y, card_w, card_h),
                              bg=PANEL_BG_HI if (sel or hov) else PANEL_BG,
                              border=color if sel else (KEY_BORDER if hov else PANEL_BORDER),
                              width=2 if sel else 1)
            self.keycap(surface, str(i + 1), (rect.x + 6, rect.y + 6))
            pygame.draw.circle(surface, color, (rect.centerx, rect.y + 34), min(r, 16))
            self.text(surface, self.f_label, name, TEXT if (sel or hov) else DIM,
                      (rect.centerx, rect.bottom - 8), "midbottom")
            self.add(rect, ("preset", i))
            x += card_w + gap

        name, _m, _r, color = presets[selected_idx]
        rect = self.panel(surface, (x, y, info_w, card_h))
        ix, iy = rect.x + 14, rect.y + 9
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

    def draw_paused(self, surface):
        img = self.f_title.render("PAUSED", True, TEXT)
        hint = self.f_label.render("Space to resume  ·  N to step", True, DIM)
        w = img.get_width() + hint.get_width() + 40
        rect = self.panel(surface, ((self.w - w) // 2, PAD, w, 34), border=ACCENT, block=False)
        surface.blit(img, (rect.x + 14, rect.y + 8))
        surface.blit(hint, (rect.x + 26 + img.get_width(), rect.y + 9))
