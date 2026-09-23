"""All tunable constants for GravSim in one place."""

# --- Window / timing -------------------------------------------------------
WIDTH, HEIGHT = 1280, 800
FPS = 60
MIN_WINDOW = (1100, 720)    # smaller windows get resized back up to this (UI needs the room)
BG_COLOR = (8, 10, 20)

# --- Physics -----------------------------------------------------------------
# Units: distance in pixels, time in seconds, mass in arbitrary "mass units".
G = 500.0
PHYSICS_DT = 1 / 240        # fixed physics step (s), independent of frame rate
DETERMINISTIC = True        # True: every frame advances exactly speed/FPS of sim time, so
                            # the same scene + inputs always play out the same way (if the
                            # PC can't keep up, the sim slows down instead of skipping).
                            # False: follow the real clock.
SIM_SEED = 12345            # seed for debris randomness (reset when a scene loads)
MAX_FRAME_TIME = 0.05       # don't try to "catch up" more than this after a stall
TIME_SPEEDS = [0.25, 0.5, 1, 2, 4, 8]   # simulation speed choices (, and . keys)
DEFAULT_SPEED_IDX = 2
REWIND_INTERVAL = 0.2       # s of sim time between rewind snapshots
REWIND_SECONDS = 60         # how much history to keep (hold Z to rewind)
REWIND_STEPS_PER_FRAME = 1  # snapshots popped per frame while Z is held (0.2 s -> 12x speed)
MAX_STEPS_PER_FRAME = 96    # safety cap so high speeds can't freeze the app
SOFTENING = 1.5             # px; avoids infinite force if r -> 0 (kept small so close orbits stay accurate)
CULL_DISTANCE = 4000        # px from view center; farther bodies are deleted
COLLISION_MODES = ("merge", "shatter", "bounce")   # M cycles through these
RESTITUTION = 0.8           # bounciness in bounce mode (1 = perfectly elastic)

# --- Launch controls -----------------------------------------------------------
SELECT_RADIUS = 30          # px; the Select tool picks the nearest body within this
CLICK_SLOP = 5               # px; a press+release shorter than this is a click, not a throw
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
PARTICLE_TRAIL_LENGTH = 45  # belts can have hundreds of particles: keep their trails short
SUN_TRAIL_LENGTH = 900      # the sun moves slowly, so it keeps a longer trail (15 s)
TRAIL_BANDS = 8             # fade is drawn in this many brightness bands

# Body presets, selected with number keys 1-6: (name, mass, radius, color)
PRESETS = [
    ("Asteroid",   1,     3, (160, 160, 160)),
    ("Moon",       5,     5, (210, 210, 220)),
    ("Planet",     20,    8, (90, 170, 255)),
    ("Gas giant",  200,  14, (230, 170, 100)),
    ("Red dwarf",  2000, 20, (255, 110, 70)),
    ("Spacecraft", 0.001, 4, (225, 232, 255)),   # has an engine + autopilot (craft.py)
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

# --- Spawn tools ----------------------------------------------------------------
RING_PARTICLES = 80         # B: particles in a ring around the selected body
RING_COLOR = (190, 180, 160)

# --- Gravity field overlay (W) ----------------------------------------------------
FIELD_CELL = 5              # grid spacing in screen px (bigger = faster, blurrier)
FIELD_LOG_TOP = 5.3         # log10 of the deepest potential shown at full brightness
FIELD_LOG_RANGE = 2.2       # decades of depth shown before fading to transparent

# --- Energy graph (E) ---------------------------------------------------------------
ENERGY_SAMPLE = 0.1         # s of sim time between samples
ENERGY_WINDOW = 30          # s of history shown

# --- Many-body performance ------------------------------------------------------
GALAXY_STARS = (1400, 900)  # test-particle stars in the two galaxies
GALAXY_CORE_SOFT = 15.0     # px softening of the galaxy cores
PARTICLE_TRAIL_LIMIT = 400  # above this many particles, particles don't draw trails

# --- Destruction (SHATTER collision mode) -----------------------------------------
SHATTER_ENERGY = 1.0        # impacts whose energy per mass beats this x G*M/R fragment (see physics.impact_severity)
SHATTER_MIN_PIECES = 4
SHATTER_MAX_PIECES = 16
ROCHE_COEFF = 0.9           # Roche limit = k * r * (M/m)^(1/3); real fluid bodies: 2.44
ROCHE_MIN_RADIUS = 3        # smaller bodies are never tidally disrupted

# --- Effects & sound ------------------------------------------------------------------
FLASH_MS = 550              # collision flash duration
GLOW_STAR_EXTENT = 5.0      # bloom radius as a multiple of body radius
GLOW_BODY_EXTENT = 3.0
SOUND_ON = True             # X toggles
SOUND_VOLUME = 0.6

# --- Spacecraft (preset 6) -------------------------------------------------------------
MANUAL_THRUST = 100.0       # px/s^2 with Up held
MANUAL_TURN_RATE = 220.0    # deg/s with Left/Right held
HOLD_KP, HOLD_KD = 6.0, 5.0     # station-keeping controller gains
HOLD_MAX_THRUST = 400.0
ORBIT_KR, ORBIT_KD = 0.8, 3.0   # orbit-hold: radial correction, velocity gain
FOLLOW_KP, FOLLOW_KD = 0.8, 3.0
FOLLOW_MAX_SPEED = 160.0    # px/s closing speed while chasing a target
FOLLOW_MAX_THRUST = 400.0
TRANSFER_MAX_THRUST = 300.0
TOUR_DWELL = 8.0            # s each Space-traffic ship orbits a planet before moving on
AVOID_LOOKAHEAD = 3.0       # s: spacecraft steer around planets/stars they'd pass this soon
AVOID_MARGIN = 35.0         # px of clearance beyond twice the body's radius
TOUR_ORBIT_GAP = 18.0       # px between a planet's surface and a touring ship's orbit
MAX_ORBITS_DRAWN = 60       # A (all orbits): cap for crowded scenes
