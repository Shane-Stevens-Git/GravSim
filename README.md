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
| **1-5** | Body type: Asteroid, Moon, Planet, Gas giant, Red dwarf |
| **Scroll** | Size of next body (mass scales with it, same density) |
| **Shift + scroll** | Mass of next body only (denser / lighter) |
| **Left-drag, release** | Throw: press where it starts, drag the way it should go |
| **Right-click** | Cancel a throw |
| **M** | Collision mode: merge / bounce |
| **L** | Trails on/off |
| **T** | Trajectory preview on/off |
| **V** | Camera: follow sun / fixed |
| **F** | Pin / unpin the sun |
| **C** / **R** | Clear thrown bodies / reset scene |
| **H** | Show / hide the controls panel |
| **Space** / **Esc** | Pause / quit |

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
