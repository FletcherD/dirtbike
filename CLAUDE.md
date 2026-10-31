# Dirt Bike 4.3 — reverse engineering, physics, planner, web game

Goal: understand Dirt Bike 4.3 (Mac OS classic, Brad Quick 1998), simulate its physics on its own
tracks/bikes, plan fast races with a lookahead AI, and play it in the browser.
Two physics cores share tracks, bike parameters, controls and the planner:
- **original** (`sim/dbcore.c`): bit-exact port of the 1998 fixed-point physics (reference, validation).
- **improved** (`sim/db2core.c`): same model and units in double precision with physics fixes (default in the web game).

## Layout

| Path | What |
|---|---|
| `dirt_bike_4.3.img_.sit` | original archive (StuffIt 5 → HFS disk image → Compact Pro .sea) |
| `game/Dirt Bike 4.3/` | extracted app (`Dirt Bike 4.3` = PPC PEF data fork, `.rsrc` = AppleDouble resource fork), docs, `Sample Tracks/` |
| `work/` | scratch artefacts: `app.pef`, `app.rsrc`, Ghidra project `work/ghidra/`, `ppc_decomp.c` (full decompilation), `ppc_listing.s` (disassembly), `mem/` (Ghidra memory dumps; data section = TOC base 0x10024120) |
| `re/symbols.txt`, `re/structs.txt` | **Ghidra annotations** (names/comments; Bike/Track/Game/TrackPt structs applied to function params). Add to these as things are understood, then run `tools/ghidra_reanalyze.sh` |
| `re/physics_step_decomp.c` | (local only, not in git) annotated decompilation of `Bike_PhysicsStep` + `Bike_Reset`; regenerate with `uv run tools/funcs.py work/ppc_decomp.c --show Bike_PhysicsStep Bike_Reset` |
| `sim/dbcore.[ch]` | original core: trig tables, RNG, bike reset/step, auto-shift, AI throttle, game substep/frame loop, track generator. Display-only wheel angles and `last_normal/last_drive` diagnostics are extra fields that don't affect physics |
| `sim/db2core.[ch]` | improved core (`Db2Bike`, `Db2Game`, tunables `Db2Config` set via `db2_set_config`) |
| `sim/dbplan_impl.h` | planner template; instantiated for each core by `sim/dbplan.c` (`db_planner_*`) and `sim/db2plan.c` (`db2_planner_*`); API in `sim/dbplan.h` |
| `sim/webapi.c` | flat C API for the web game (one track, one bike, either core) |
| `dirtbike/` | Python package (uv project): `formats.py` file loaders, `sim.py` ctypes wrapper (`core("original"/"improved")`, auto-builds `sim/build/libdbcore.so`), `planner.py`, `runio.py` (CLI helpers, run JSON), `viewer.html` (run viewer template) |
| `tools/` | CLIs (below) and RE helpers: `appledouble.py`, `funcs.py` (grep/print functions in `ppc_decomp.c`), `pefdata.py` (vtables/doubles in the data section), `ghidra_scripts/` |
| `runs/` | planner/sim outputs: `<name>.json` + `<name>.html` (self-contained viewer) |
| `web/` | the browser game (static site): `index.html`, `game.js` (hand-written); `tracks/index.json` + `tracks/<track>.json` (points + high-score ghosts) and `sounds/<event>.wav`, generated locally by `tools/build_web.py` from the original game files and committed; `physics.js` + `physics.wasm` (generated, not committed — built by CI) |

## Tools

All use `uv run tools/<x>.py --help` (defaults shown). Track spec: sample track name (`Speed`, `"Hill Climb"`,
`"Ups and Downs"`, `"Watch That Drop"`, `"Untitled Track"`), a path, `beginner`, `expert`, or `seed:N`.
Bike spec: `expert`, `beginner`, or a BIKE/setup file. `--physics original|improved`; improved-core tunables
via repeatable `--set key=value` (keys = `Db2Config` fields).

- `tools/plan.py --track Speed [--beam 3000] [--manual-shift] [--max-tilt 60 --max-rpm 60000 --frames-per-step 6]` —
  full-race beam search, verified by re-simulation, writes `runs/`. The bracketed options give a "reasonable
  rider" (no flips beyond 60°, no over-revving, 120 ms decisions).
- `tools/simulate.py --track Speed --throttle 0:30000,3:45000` or `--plan runs/X.json` — harness run.
- `tools/track_replay.py --track Speed --replay 0 --manual --frame-units-list 290,330` — validation: search inputs that
  follow a recorded high-score trajectory. `--time-scale` converts the recording's clock (≈1.1 for an exact-clock core).
- `tools/ablate_improved.py` — tracking error with each improved-core change enabled alone (feel check).
- `tools/calibrate_mu.py` — |drive|/|N| distribution along human replays (basis for the improved core's `mu`).
- `tools/bench.py` — planner over tracks × settings × cores.
- `tools/extract_images.py` — all PICTs → `work/images/pict/`, masked sprites → `work/images/sprites/`, Finder icons
  → `work/images/icons/`, gallery `work/images/index.html`. 1-bit bitmap PICTs (the masks, v1 and v2) are decoded
  in-script (ImageMagick misreads them); colour PICTs go through ImageMagick `convert`.
- `tools/analyze_sprites.py`, `tools/render_scenery.py` — sprite rotation/pose analysis and original-style scenery
  reconstruction (outputs in `work/images/`).
- `tools/extract_sounds.py` — `snd ` resources → `work/sounds/snd<id>.wav` (MACE 3:1 decoded by ffmpeg via AIFF-C).
- `tools/build_web.py [--only wasm tracks sounds]` — compile `sim/webapi.c`+cores with emcc (apt `emscripten`) into
  `web/physics.js` + `physics.wasm`, export sample tracks + ghosts to `web/tracks/` and copy sound effects to
  `web/sounds/<event>.wav` (the original music, snd 200, is deliberately not shipped). `--only wasm` needs no project
  deps (used by CI). The game fetches its files, so serve it: `python3 -m http.server -d web`.
- `tools/ghidra_reanalyze.sh` — apply `re/*.txt` to the Ghidra project, regenerate `work/ppc_decomp.c` + `work/ppc_listing.s`. Ghidra 12.2 in `~/opt/ghidra_12.2_PUBLIC`.

Re-extracting from scratch: `unar` the .sit → `hmount`/`hcopy -m` (hfsutils) the `.sea` out of the HFS image →
`unar -forks visible` it → `tools/appledouble.py` to get the raw resource fork (`work/app.rsrc`).

## The binary

Fat app: PPC code in the data fork (PEF, CodeWarrior C++, no symbols) — this is what we analyse; 68k
CODE resources also exist but are unused here. Virtual calls go through `__ptr_glue` (0x10022828) with
`lwz r12,slot(vptr)`; vptr is the first word of objects. Bike vtable `0x10027ac8` (+0x1c Reset, +0x20
PhysicsStep, +0x2c SetFinished, +0x30 UpdateThrottle); ComputerBike `0x10027bac`; LocalBike overrides
+0x20/+0x30 (`0x10017c40`, `0x10017cc8`). Strings and TVectors are in the data section; `tools/pefdata.py`.
Images (`PICT`): 128–157 bike+rider sprites, one per angle bucket (degree→index table built in `InitTrigTables`,
level = 143), drawn at CG + per-index offsets (`g_game+0xf8` x / `+0x170` y, mm, set in `FUN_1000f574`), 30 mm
per sprite pixel; 158–165 wheel sprites (brown/blue/red/yellow, two frames each), centred on the wheel hubs;
masks are id+1000 (black = draw); 180 scenery strip (start sign, cactus); 201 about-box photo; 1000 title screen;
2000/2001 background panoramas. Bike drawing: `FUN_100147c8`.
- Sprite analysis (`tools/analyze_sprites.py`): the bike body in 128–157 is a rigid rotation about the CG at the
  bucket-centre angle (±2°; offsets accurate to ~5 px), but the rider is re-posed per sprite: steeply nose-up he
  lies forward over the bars (up to ~22° less rotated than the bike), steeply nose-down he leans back over the rear;
  level/inverted = normal crouch. Angle buckets are 5° wide near level, up to 28° near inverted.
- Ground (`Track_BuildScenery` @1001ac60, reconstructed by `tools/render_scenery.py`): one pre-rendered bitmap per
  lap at `scale` mm/px — panorama 2000/2001 stretched to the bitmap height and mirror-tiled; dirt = 1 px black
  `MoveTo/LineTo` per column from the surface down (no colour set → default black pen); strip-180 items stand on
  the surface (`FUN_1001a984` sub-rects: plants 1–3, bush 4, cactus 5, GO sign 6, item 7); the grass is item 8: at
  every track point a random 3×4 px slice of the strip's rows 46–49 (x 133–299, brown/green texture) is CopyMasked
  with its top at the surface, giving a 4 px textured crust. The gameplay view copies from this bitmap, wrapping
  horizontally by the lap width.
Sounds (`snd `): 128 engine loop (playback rate set to rpm+40000, presumably /65536), 129 go, 130 crash,
131 "keep it up" (lap), 132 bottom out, 133 "whoa" (full rotation), 134 hooray, 200 music (starts with the countdown).

## File formats (data fork, big-endian, chunked: u32 tag, u32 len, payload)

In memory, payload offset = object offset − 4 (objects start with a vptr).
- **Track** (`TRAK`): tag 2, 0x7e64 bytes: +2 description (C string), +0xe4 laps (i16), +0xe8 allow-get-back (i16),
  +0xf4 nPoints (i16, ≤4000), +0xf8 points (i32 x, i32 y)×n, +0x7df8 high-score count (i16), +0x7dfa file name,
  +0x7e60 seed. Then per high score: tag 3, 0x882c bytes replay: +0 count (i16), +4 wheel radii, +8 samples
  of 0x18 bytes (i32 x, i32 y, i16 fwx−x, fwy−y, rwx−x, rwy−y, i16 theta_mrad, pad, i32 race_time), name at +0x87f8.
  Replays are trajectories (no inputs), sampled ~every 100 ms. The web game stores your best ghost in the same layout.
- **Bike** (`BIKE`): one chunk whose first 0x60 bytes = parameter block (see `DbBikeParams` / `formats.parse_bike_params`).
- **Setup** (`SETU`): tags 11, 2 (track), 4 (local player: 0x60 bike block + name …), 7, 9, 10.
- Built-in Beginner's/Expert's tracks are generated from seeds 0x5b694da2 / 0x25dd37d2 (`db_track_generate`,
  bit-exact vs `Untitled Track`). Beginner's/Expert's bikes: `db_bike_set_beginner/expert`.

## Physics model (original; see `sim/dbcore.c` for the exact integer arithmetic)

Units: positions mm (+y up), dt in 0.1 ms of game time, velocities 0.1 mm/s, forces 0.1 N, angles in degrees
(table index, 180 = level, front wheel toward +x; <180 = nose up) and milliradians (`theta`), trig tables ×1024.
- Track = polyline of points (spacing ~50 mm). Wheel contact considers only **vertices** inside the wheel
  circle: penalty force (R−d)·100 along the vertex→centre direction, summed (≈ F = 71·δ^1.5 for the stock wheel
  on 50 mm tracks). A wheel whose x-span has no vertex below its centre is "under ground" → crash.
- Each wheel is on a 1-D suspension (spring rate, travel, compression/rebound damping, wheel mass). Front fork is
  tilted by the rake angle. Hitting either end of the travel transfers the wheel momentum to the body.
- Rear wheel drive: torque from (throttle − rpm) × power curve (or brake power when throttle is 0) × gear
  ratio; the drive force is the rear contact force N rotated 90°, scaled by torque / |N|₁, so its magnitude is
  ≈ torque·|N|/|N|₁ (1 on flat ground, 0.71 on 45° slopes) **independent of how hard the wheel presses** — any
  contact gives full traction, no friction limit.
- rpm = (vx + |vy|) × ratio / 128 when the rear wheel touches, else rpm jumps to the throttle target.
- Body: point mass + moment of inertia from wheel/body masses and distances; gravity 9.8 m/s².
  **Gyration**: change in rear-wheel spin (∝ rpm/ratio) applies an opposite body rotation — throttle up = nose up.
- Crash: wheel under ground, or angle <45°/>315° while touching. With "get back on" the bike respawns 2 m above
  the rear wheel's track point with zero velocity, otherwise it is out (DNF).
- Lap: passing x > pts[n−40].x wraps to the start region (track repeats its first 100 points at the end).
- Controls: throttle = target engine rpm 0…58800 = (294 − mouseY_global)·200 (mouse) or ±15·dt per substep
  (keys). Throttle 0 = brake. Gears 0 (neutral)…5; manual shift with arrow keys / mouse click; auto shift: up at
  rpm>40000 if angle>170 and rear touching; down at rpm<20000. First upshift starts the engine; gears engage once racing.
- Game loop (`Game_Substep`): elapsed µs/83 accumulates into `acc`; each frame is split into 1–7 substeps
  (`dt = acc/nsub`, acc capped at 700). Race state: 0 wait for all engines → 1 countdown (1000 ms) → 2 racing.
  Race time += dt/10 per substep **with truncation**, so the clock under-counts when dt is not a multiple of 10
  (Brad's recordings: ≈1.1×). frame_units=200 → 4 substeps of dt=50 (exact clock, ~60 fps).
- Integer truncation creates dead zones: position/suspension/rotation updates of the form `((v/10)·dt)/10000` drop
  motion slower than ~0.2 m/s and lose up to 1 mm per step (5–10% of speed at ~2 m/s). This acts like stiction.
- **Overflow exploit**: holding a low gear at high speed (manual shifting) makes rpm ≫ throttle; the torque
  product overflows int32 and the huge negative engine braking wraps into a huge forward drive (planner reaches 70 m/s).
- Computer bikes (`player_type` 8) use `RandRange` (ANSI LCG, `g_randSeed` starts at 1) for their throttle logic.

## Improved core (`sim/db2core.h`)

Same equations/units/parameters/controls/rules, in doubles, with: fixed 5 ms step and exact clock; continuous
segment-integral contact with the original's 50 mm stiffness; contact damping; drive force normalised by the
Euclidean norm (no slope penalty); traction unlimited like the original (optional cap `mu`: a realistic μ≈1 would
keep only ~23% of the drive impulse humans use in the original, μ=20 ~89%, see `tools/calibrate_mu.py`); engine/wheel spin lags the throttle when not ground-driven (bounded gyration);
rpm from rolling speed along the ground; "under ground" = centre below the surface; laps wrap by exact
translation. `Db2Config` switches (`contact_continuous`, `rolling_rpm`, `surface_under`) and tunables can
restore original behaviour piecewise. Known differences: no first dt=1 substep (starts 1 frame earlier);
removing truncation alone already changes low-speed feel (faster creep, no suspension stiction), so human
replays can't be tracked with it (`tools/ablate_improved.py`); same-input open-loop runs diverge within seconds.

## Validation status (original core)

- Settled pose at start matches the original replays (y, wheel offsets, theta within a few mm/mrad).
- Track generator bit-exact against `Untitled Track` (all 4000 points).
- `tools/track_replay.py --manual`: four of Brad's high-score races (Speed ×2, Ups and Downs, Watch That Drop)
  reproduced over 30–45 s with RMS position error ~12–27 cm and ~40–90 mrad, using the Expert bike, manual
  shifting, frame_units ≈ 290–330 (his Mac ran ~24 fps), or frame_units 200 with `--time-scale 1.1`. Some settings
  fail only because the tracking beam loses the trajectory. Hill Climb replays used a modified bike (front radius 225).
- Not ported: graphics/scenery, network play, track editor, replay recording format writer.

## Planner

`*_planner_*` (C, OpenMP): beam search over actions = throttle level (+ optional shift) held for
`frames_per_step` frames. Children are bucketed by (progress, angle, vy, gear, engine/race state) keeping the
best per bucket, then the top `beam_width` by score = progress + vel_weight·vx (finished: by finish time;
crash = dropped unless the track allows getting back on, then penalised; `max_tilt`/`max_rpm` prune
unreasonable branches). Tracking mode (targets) scores by error to a recorded trajectory. Deterministic; plans are
verified by re-simulating. Unconstrained, it finds TAS-style exploits (flips, gyration hops, the overflow).
Reasonable-rider results (manual, tilt ≤60°, rpm ≤60000): original Speed 25.1 s / Ups and Downs 43.4 s /
Watch That Drop 29.8 s; improved 23.1 / 39.0 / 30.2 s; Brad's records 30.1 / 44.8 / 31.1 s (his clock ≈1.1× slow).

## Run viewer (`dirtbike/viewer.html`)

Written next to each run JSON by `runio.write_run`. Bike with spoked rotating wheels, ghosts from the track file,
throttle gauge drawn like the mouse-height control (brake zone below 294/480), gear/rpm, a timeline strip of
throttle (red = brake) / gear / speed with crash (red) and lap (white) marks; click the strip to seek, space
play/pause, arrows step frames (shift ×10).

## Web game (`web/`)

`game.js` loads `physics.js` (MODULARIZE, `DirtBikePhysics()`, fetches `physics.wasm`) and `tracks/index.json`
(menu: names, descriptions, laps, record times; track JSON fetched on race start, sounds on first race), writes track points / the 27-int bike parameter
block (`PARAM_NAMES`) into wasm memory, calls `_web_new_race(improved, 0)`, then per animation frame
`_web_set_throttle`, `_web_advance(elapsed ms × 10)` and reads `_web_state()` (26 doubles, index map `S` in
game.js / enum in webapi.c). Events (go, crash, lap, flip, bottom-out, finish) are detected by diffing states.
Menu: track (samples, generated Beginner/Expert, random seed), bike (Expert/Beginner/Custom via the editor),
physics core, transmission, ghosts/sound/music. Best times + your best ghost in localStorage per
track/physics/bike. Rendering reuses the viewer's bike/wheel/HUD code plus a rider modelled on sprite 143 that leans like the original
sprites (`riderLean`: 0 near level/inverted, up to 22° forward when nose-up / back when nose-down; torso pivots at
sliding hips, two-bone `joint` keeps feet on the pegs and hands on the bars), parallax hills, lap line. Ground
decoration (`buildDecor`, seeded per track, chunked by 100 points and culled to the view) follows a biome
(`BIOMES`: palette, surface layers, plant types with spacing; menu "Scenery", auto = hash of the track id):
grassland = speckles, grass crust and blades, plants, puffy bushes, creosote; desert = sand with pebble speckles,
rocks, saguaro/barrel cacti and L-system plants. `lPlant` expands a stochastic L-system (`L_PLANTS`: creosote,
ocotillo; F/+/-/[ ] turtle with angle/length jitter, flowers at some tips) into a Path2D once per plant. The track is drawn three times, shifted by ±(pts[n−100] − pts[0]), because the world repeats every lap.

## Repository and deployment

Git repo (GitHub `FletcherD/dirtbike`, branch `main`). `.gitignore` keeps the original game archive, extracted
files (`extract/`, `raw/`, `game/`), Ghidra workspace (`work/`), run outputs, builds and the decompiled excerpt out
of git. `.github/workflows/pages.yml` builds `web/physics.js` with emsdk and deploys `web/` to GitHub Pages
(https://fletcherd.github.io/dirtbike/) on pushes touching `web/`, `sim/` or the build script. After changing
tracks/sounds extraction, rebuild them locally (`uv run tools/build_web.py --only tracks sounds`) and commit.
