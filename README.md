# Dirt Bike

A browser remake of **Dirt Bike 4.3** (Mac OS classic, Brad Quick & Michel de Messieres, 1998), built on a
reverse-engineered port of the original physics.

- **Play:** open `web/index.html` (works straight from the filesystem) or the GitHub Pages site.
  Throttle is the height of the mouse; → / click shifts up (and starts the engine), ← shifts down.
- `sim/` — C physics: `dbcore.c` is a bit-exact port of the original fixed-point physics, `db2core.c` an
  improved floating-point version (default in the game), `webapi.c` the WebAssembly interface.
- `dirtbike/`, `tools/` — Python harness: file loaders, simulation, beam-search race planner, replay validation,
  run viewer, web build (`uv run tools/build_web.py`, needs `emcc`).
- `re/` — Ghidra annotations from the reverse engineering.

See `CLAUDE.md` for the full technical description. Building the web game's data and validating against the
original needs the original game archive, which is not included in this repository.
