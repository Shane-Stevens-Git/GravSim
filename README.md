# GravSim

A 2D interactive gravity sandbox in Python + pygame. Every body pulls on
every other body with real inverse-square gravity (velocity-Verlet
integration, vectorized with NumPy), so orbits, slingshots, collisions and
ejections all emerge from the physics.

## Run

```
pip install -r requirements.txt
python main.py
```

## Controls

| Input | Action |
|---|---|
| **1-6** or click a card | Body type: Asteroid, Moon, Planet, Gas giant, Red dwarf, Spacecraft |
| **Scroll** | Size of next body (mass scales with it, same density) |
| **Shift + scroll** | Mass of next body only (denser / lighter) |
| **Left-drag, release** | Throw: press where it starts, drag the way it should go |
| **Right-click** | Cancel a throw |
| **Q** or the Select card | Select tool: clicks pick the nearest body (within ~30 px) and never create one; drag to pan. 1-6 switches back to throwing |
| **Arrow keys** | Fly the selected spacecraft in Manual mode (Up thrust, Down brake, Left/Right turn) |
| **Click a body** | Select it: inspector shows its orbit (period, eccentricity, peri/apoapsis) and draws the predicted ellipse |
| **G** | Camera follows the selected body (again: back to the sun) |
| **[ / ]**, **Del** | Lower / raise the selected body's mass (x1.5), delete it |
| **Ctrl + scroll**, **+ / -** | Zoom in / out (0 resets) |
| **Middle-drag** | Pan the view (switches the camera to fixed) |
| **M / L / T / V** | Collision mode (merge / shatter / bounce), trails, aim preview, camera follow (or click the rows) |
| **S** | Show / hide the sun panel |
| **P** | Scenes menu (then 1-6 or click to load a preset) |
| **O** | Orbit tool: a click places the next body on a circular orbit around whatever pulls hardest there (Shift+click: other direction) |
| **B** | Add a ring of particles around the selected body (inside its Hill sphere) |
| **W** | Gravity field overlay: potential wells as a heatmap with contour lines |
| **E** | Energy & momentum graph (hover for values). Flat = conserved; steps = something was added or merged |
| **X** | Sound on / off (collision sounds are synthesized, no audio files) |
| **Z** (hold) | Rewind, up to 60 s back (clicking the Rewind row jumps back 5 s) |
| **K** | Show Lagrange points L1-L5 (for the selected body and what it orbits) |
| **Ctrl+S** / **Ctrl+O** | Save / load a scene file (saved in `saves/`) |
| **F5** / **F9** | Quick save / quick load |
| **F** | Pin / unpin the sun |
| **H** | Show / hide the controls panel |
| **C** / **R** | Clear thrown bodies / reset scene |
| **Space** / **N** | Pause / step one frame |
| **,** / **.** | Slower / faster (0.25x to 8x, or click the Speed row) |
| **Esc** | Quit |

### Collision modes (M)

- **Merge** - bodies that touch combine; mass, momentum and volume are kept.
- **Shatter** - like merge, but impacts faster than 2x the pair's mutual
  escape speed fragment: the bigger body keeps a remnant (smaller for harder
  hits) and the rest sprays out as debris. Bodies that stray inside a heavier
  body's **Roche limit** are torn apart by tides into a debris stream. Try
  throwing a planet so it just grazes the sun.
- **Bounce** - elastic-ish bounces (restitution 0.8).

### Scenes

| Scene | What to watch |
|---|---|
| Sun & planet | The default elliptical orbit. |
| Inner solar system | Four planets; select Earth and press G to watch its moon. |
| Binary star | A planet on a stable orbit around *both* stars. |
| Figure-eight | Three equal stars sharing one figure-8 path. Marginally stable - it eventually breaks up. |
| Asteroid belt | 300 test-particle asteroids; the giant's 2:1 resonance stirs up the middle of the belt (try 8x). |
| Lagrange points | Asteroids at L1-L5. L4/L5 (green) hold them in tadpole loops; L1-L3 (amber) are unstable, so those drift off - while **probes** beside the L1 and L2 asteroids hold those points with small thruster burns (station-keeping). |
| Galaxy collision | 2,300 stars in two disk galaxies on a close, bound fly-by: tidal tails, bridges, stolen stars; the cores come back and merge. Try 4x. |
| Shatter demo | Switches to SHATTER mode: a head-on planet/giant smash at ~2 s, a planet shredded by the sun's tides at ~3 s, and the smash remnant falling sunward to be shredded too. |

**Test particles:** belt asteroids, Lagrange asteroids and galaxy stars feel
gravity but exert none and never collide with each other (like real
asteroids/stars, whose pull on each other is negligible here). Gravity then
costs particles x massive bodies instead of everything squared, so thousands
of particles run in real time; above 400 particles they're drawn as dots and
skip trails. Galaxy cores are softened (their mass is spread out) and let
stars pass through instead of swallowing them.

R restarts the current scene (or reloads the last scene file).

### Spacecraft (6)

Throw one like any body; it's selected automatically and the inspector gets
an **Autopilot** row. Fuel is unlimited, but the delta-v spent is shown.

- **Hold** - station-keeping. Near a shown Lagrange point (K) it holds that
  point; otherwise it holds a circular orbit at its current distance.
- **Transfer** - click a planet: waits for the launch window, does a
  Hohmann transfer burn, coasts, then rendezvous.
- **Follow** - click a body: rendezvous and keep station beside it, or enter
  orbit around it if it's massive enough to hold one.
- **Manual** - fly it with the arrow keys.
- **Off** - engine off, just coasting.

Spacecraft fly through dust and debris (test particles) but crash into
planets and stars.

### Sun panel

Pick a star type (red dwarf, yellow star, blue giant, white dwarf, black
hole), or drag the mass and radius sliders. Changes apply live, so existing
orbits react to them. **Recenter** moves the whole system back to the view
center and brings the sun to rest without changing how anything moves
relative to it. **R** resets the scene with the current sun settings.

Tip: the HUD shows the circular-orbit speed at your launch point. Drag
sideways to the sun at about that speed for a circle; about 1.4x escapes.

Tunables (G, time step, restitution, trail length, slingshot-style
aiming, effects, sound volume, ...) are constants in `config.py`.

## Code layout

| File | What's in it |
|---|---|
| `main.py` | entry point |
| `app.py` | the App: input, update loop, drawing |
| `physics.py` | gravity (NumPy), Verlet integration, collisions, orbits, Roche limit |
| `body.py` | Body and the camera View |
| `scenes.py` | preset scenarios, Lagrange solver, spawn tools, save/load |
| `history.py` | rewind buffer |
| `field.py` | gravity field overlay |
| `effects.py` | parallax starfield, collision flashes |
| `sound.py` | synthesized collision sounds |
| `ui.py` | on-screen panels |
| `render.py` | small drawing helpers |
| `config.py` | all tunable constants |

## Roadmap

1. [x] Window + a single static sun
2. [x] One moving body with real inverse-square gravity toward the sun
3. [x] Click-and-drag to launch new bodies with custom mass/size/velocity
4. [x] Full n-body attraction
5. [x] Polish: trails, collisions (merge/bounce), mass/size controls
