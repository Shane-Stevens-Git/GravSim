"""All tunable constants for GravSim in one place."""

# --- Window / timing -------------------------------------------------------
WIDTH, HEIGHT = 1280, 800
FPS = 60
BG_COLOR = (8, 10, 20)

# --- Physics -----------------------------------------------------------------
# Units: distance in pixels, time in seconds, mass in arbitrary "mass units".
G = 500.0
PHYSICS_DT = 1 / 240        # fixed physics step (s), independent of frame rate
MAX_FRAME_TIME = 0.05       # don't try to "catch up" more than this after a stall
TIME_SPEEDS = [0.25, 0.5, 1, 2, 4, 8]   # simulation speed choices (, and . keys)
DEFAULT_SPEED_IDX = 2
MAX_STEPS_PER_FRAME = 96    # safety cap so high speeds can't freeze the app
SOFTENING = 5.0             # px; avoids infinite force if r -> 0
CULL_DISTANCE = 4000        # px from view center; farther bodies are deleted
RESTITUTION = 0.8           # bounciness in bounce mode (1 = perfectly elastic)

# --- Launch controls -----------------------------------------------------------
LAUNCH_SCALE = 1.0          # launch speed (px/s) per pixel dragged
SLINGSHOT = False           # False: drag the way it should go. True: pull back like a slingshot.
PREVIEW_STEPS = 320         # trajectory preview length (steps of PREVIEW_DT)
PREVIEW_DT = 1 / 40
PREVIEW_MAX_BODIES = 12     # preview only simulates the heaviest bodies (for speed)
SCROLL_STEP = 1.15          # size/mass multiplier per scroll notch
SIZE_RANGE = (0.3, 4.0)
MASS_RANGE = (0.05, 20.0)

# --- Trails ------------------------------------------------------------------
TRAIL_LENGTH = 240          # frames of history per body (4 s at 60 fps)
SUN_TRAIL_LENGTH = 900      # the sun moves slowly, so it keeps a longer trail (15 s)
TRAIL_BANDS = 8             # fade is drawn in this many brightness bands

# Body presets, selected with number keys 1-5: (name, mass, radius, color)
PRESETS = [
    ("Asteroid",   1,     3, (160, 160, 160)),
    ("Moon",       5,     5, (210, 210, 220)),
    ("Planet",     20,    8, (90, 170, 255)),
    ("Gas giant",  200,  14, (230, 170, 100)),
    ("Red dwarf",  2000, 20, (255, 110, 70)),
]


# Sun types for the sun panel: (name, mass, radius, color, kind)
SUN_TYPES = [
    ("Red dwarf",   4_000,  22, (255, 120, 80),  "star"),
    ("Yellow star", 10_000, 30, (255, 200, 60),  "star"),
    ("Blue giant",  25_000, 45, (150, 185, 255), "star"),
    ("White dwarf", 8_000,  10, (235, 240, 255), "star"),
    ("Black hole",  40_000, 12, (0, 0, 0),       "blackhole"),
]
DEFAULT_SUN = 1
SUN_MASS_RANGE = (1_000, 100_000)   # sun panel slider (log scale)
SUN_RADIUS_RANGE = (5, 80)
BLACK_HOLE_RING = (255, 150, 70)   # black-hole accretion ring

# --- Camera -------------------------------------------------------------------
ZOOM_RANGE = (0.1, 5.0)
ZOOM_STEP = 1.15            # zoom factor per Ctrl+scroll notch or +/- press
