"""GravSim - a 2D interactive gravity sandbox.

Real inverse-square n-body gravity. Pick a body type (1-5), fine-tune
its size/mass with the scroll wheel, then click-drag-release to throw it.
Bodies orbit, collide (merge or bounce), or get flung out of the scene.

Modules:
  config.py   tunable constants
  physics.py  gravity, integration, collisions, orbit math
  body.py     Body and the camera View
  scenes.py   building scenes
  render.py   drawing helpers
  ui.py       on-screen panels
  app.py      the App: input, update loop, drawing
"""
from app import main

if __name__ == "__main__":
    main()
