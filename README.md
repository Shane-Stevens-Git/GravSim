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
| **1-5** or click a card | Body type: Asteroid, Moon, Planet, Gas giant, Red dwarf |
| **Scroll** | Size of next body (mass scales with it, same density) |
| **Shift + scroll** | Mass of next body only (denser / lighter) |
| **Left-drag, release** | Throw: press where it starts, drag the way it should go |
| **Right-click** | Cancel a throw |
| **Ctrl + scroll**, **+ / -** | Zoom in / out (0 resets) |
| **Middle-drag** | Pan the view (switches the camera to fixed) |
| **M / L / T / V** | Collisions merge/bounce, trails, aim preview, camera follow (or click the rows) |
| **S** | Show / hide the sun panel |
| **F** | Pin / unpin the sun |
| **H** | Show / hide the controls panel |
| **C** / **R** | Clear thrown bodies / reset scene |
| **Space** / **Esc** | Pause / quit |

### Sun panel

Pick a star type (red dwarf, yellow star, blue giant, white dwarf, black
hole), or drag the mass and radius sliders. Changes apply live, so existing
orbits react to them. **Recenter** moves the whole system back to the view
center and brings the sun to rest without changing how anything moves
relative to it. **R** resets the scene with the current sun settings.

Tip: the HUD shows the circular-orbit speed at your launch point. Drag
sideways to the sun at about that speed for a circle; about 1.4x escapes.

Tunables (G, time step, restitution, trail length, slingshot-style
aiming, ...) are constants at the top of `main.py`.

## Roadmap

1. [x] Window + a single static sun
2. [x] One moving body with real inverse-square gravity toward the sun
3. [x] Click-and-drag to launch new bodies with custom mass/size/velocity
4. [x] Full n-body attraction
5. [x] Polish: trails, collisions (merge/bounce), mass/size controls
