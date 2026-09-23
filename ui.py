"""On-screen UI for GravSim: status panel, controls panel, body toolbar,
and the aiming readout. Pure drawing - main.py owns all the state."""
import math

import pygame

# --- Palette -------------------------------------------------------------------
TEXT = (222, 227, 240)
DIM = (122, 131, 156)
ACCENT = (120, 170, 255)
PANEL_BG = (14, 18, 32, 215)
PANEL_BG_HI = (30, 37, 62, 235)
PANEL_BORDER = (52, 62, 92)
KEY_BG = (36, 44, 70)
KEY_BORDER = (80, 92, 130)

# Orbit-status colors used by the aim readout (and the aim arrow)
GOOD = (110, 220, 150)
INFO = (120, 170, 255)
WARN = (245, 185, 85)
BAD = (240, 100, 90)

PAD = 12


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
        self._panel_cache = {}

    # --- Primitives ------------------------------------------------------------
    def panel(self, surface, rect, bg=PANEL_BG, border=PANEL_BORDER, width=1, radius=10):
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
        pygame.draw.rect(surface, (40, 48, 74), rect, border_radius=2)
        fill = rect.copy()
        fill.width = max(2, round(rect.width * min(max(t, 0), 1)))
        pygame.draw.rect(surface, color, fill, border_radius=2)

    # --- Status panel (top-left) -------------------------------------------------
    def draw_status(self, surface, fps, n_bodies, sim_time, toggles):
        """toggles: list of (key, label, value_text, is_on)."""
        row_h = 24
        rect = self.panel(surface, (PAD, PAD, 250, 78 + row_h * len(toggles)))
        x, y = rect.x + 14, rect.y + 12
        self.text(surface, self.f_title, "GRAVSIM", ACCENT, (x, y))
        self.text(surface, self.f_num, f"{fps:3.0f} fps", DIM, (rect.right - 14, y + 1), "topright")

        y += 28
        for i, (label, value) in enumerate((("Bodies", f"{n_bodies}"), ("Time", f"{sim_time:6.1f} s"))):
            cx = x + i * 112
            self.text(surface, self.f_label, label, DIM, (cx, y))
            self.text(surface, self.f_num, value, TEXT, (cx + 52 if i == 0 else cx + 40, y + 1))

        y += 26
        pygame.draw.line(surface, PANEL_BORDER, (rect.x + 10, y - 6), (rect.right - 10, y - 6))
        for key, label, value, on in toggles:
            self.keycap(surface, key, (x, y))
            self.text(surface, self.f_label, label, TEXT, (x + 30, y + 1))
            self.text(surface, self.f_small, value, ACCENT if on else DIM,
                      (rect.right - 14, y + 3), "topright")
            y += row_h

    # --- Controls panel (top-right) -----------------------------------------------
    CONTROLS = [
        ("Drag", "Throw a body"),
        ("RMB", "Cancel throw"),
        ("1-5", "Choose body type"),
        ("Scroll", "Resize (keeps density)"),
        ("Shift+Scroll", "Change mass only"),
        ("Space", "Pause / resume"),
        ("C", "Clear thrown bodies"),
        ("R", "Reset scene"),
        ("Esc", "Quit"),
    ]

    def draw_controls(self, surface):
        if not self.show_help:
            label = self.f_label.render("Controls", True, DIM)
            rect = self.panel(surface, (self.w - PAD - label.get_width() - 58, PAD,
                                        label.get_width() + 58, 34))
            self.keycap(surface, "H", (rect.x + 12, rect.y + 8))
            surface.blit(label, (rect.x + 42, rect.y + 8))
            return
        row_h, key_w = 24, 96
        rect = self.panel(surface, (self.w - PAD - 270, PAD, 270, 50 + row_h * len(self.CONTROLS)))
        x, y = rect.x + 14, rect.y + 12
        self.text(surface, self.f_title, "CONTROLS", ACCENT, (x, y))
        hide = self.text(surface, self.f_label, "hide", DIM, (rect.right - 14, y + 1), "topright")
        self.keycap(surface, "H", (hide.x - 26, y))
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
            rect = self.panel(surface, (x, y, card_w, card_h),
                              bg=PANEL_BG_HI if sel else PANEL_BG,
                              border=color if sel else PANEL_BORDER, width=2 if sel else 1)
            self.keycap(surface, str(i + 1), (rect.x + 6, rect.y + 6))
            pygame.draw.circle(surface, color, (rect.centerx, rect.y + 34), min(r, 16))
            self.text(surface, self.f_label, name, TEXT if sel else DIM,
                      (rect.centerx, rect.bottom - 8), "midbottom")
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
                          border=color if label else PANEL_BORDER)
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
        hint = self.f_label.render("Space to resume", True, DIM)
        w = img.get_width() + hint.get_width() + 40
        rect = self.panel(surface, ((self.w - w) // 2, PAD, w, 34), border=ACCENT)
        surface.blit(img, (rect.x + 14, rect.y + 8))
        surface.blit(hint, (rect.x + 26 + img.get_width(), rect.y + 9))
