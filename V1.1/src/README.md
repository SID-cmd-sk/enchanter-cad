# PyCAD — standalone Python CAD app (AutoCAD-workflow clone, v1)

## What this is
A real, working PyQt6 desktop CAD app:
- Command-line driven, AutoCAD style (`L`, `C`, `M`, `TR`, ... same aliases as the shortcuts guide)
- Native DXF read/write (`ezdxf`)
- DWG read/write via the free **ODA File Converter** (see DWG section below)
- Canvas: pan (middle-drag), zoom (wheel), click-to-place points, window/crossing selection
- ~30 fully working commands: LINE, CIRCLE, ARC, PLINE, RECTANG, POLYGON, POINT, TEXT/MTEXT,
  MOVE, COPY, ROTATE, SCALE, MIRROR, ERASE, OFFSET, FILLET, CHAMFER, STRETCH, EXPLODE, JOIN,
  ARRAY, UNDO, REDO, DIST, AREA, LAYER, PURGE, REGEN/REDRAW, SELECTALL
- Every alias from the Autodesk Shortcuts Guide (150+) is recognized at the command line —
  unimplemented ones print an honest message instead of crashing (see `command_table.py`)
- One-click **G-CODE** button: direct Python port of `GCODEGEN_.lsp` (same math — WriteSegment,
  BulgeToArcPts, lead-in/out, multi-pass, zig-zag continuous, cutter comp), with live preview

## Parametric modeling (constraints + design variables)
PyCAD is now a **parametric** CAD: geometry is driven by constraints, like
SolidWorks. (`constraints.py` + the `Drawing.constraints`/`variables` store.)

- **Auto-constrain** (`AC` / `FULLYDEFINE`): infers geometric relations from
  existing geometry — coincident endpoints, horizontal/vertical lines,
  parallel/perpendicular pairs, concentric circles, equal lengths/radii — and
  adds them automatically.
- **Manual constraints** (`CON` / `DC`): COINCIDENT, HORIZONTAL, VERTICAL,
  PARALLEL, PERPENDICULAR, EQUAL, CONCENTRIC, TANGENT, MIDPOINT, plus
  dimensional DISTANCE / RADIUS / DIAMETER / ANGLE.
- **Design variables** (`VAR` / `PAR`): named parameters (e.g. `W=100`). A
  dimensional constraint can be *linked* to a variable, so editing one value
  (`REBUILD`) re-solves the whole sketch. Grip-editing on canvas re-solves live.
- Solver is an iterative Gauss-Seidel relaxation; `REBUILD` (or any edit)
  snaps geometry back onto its constraints.

## Post-processor system (multi-machine G-code)
G-code is generated through a pluggable **post-processor** layer. The geometry
engine (`gcode.py`) emits *controller-neutral* toolpath events
(`emit_path_to_events`); the selected post turns those into machine-specific
G-code.

- **One machine = one `.py` file** in the `posts/` folder. PyCAD
  **auto-discovers** every post file — drop in 1 file, get 1 post; drop in 20,
  get 20. No registry, no JSON, nothing to recompile. See `posts/README.md`
  for the full format and a copy-paste template.
- Built-in posts: **Fanuc, Haas, LinuxCNC, GRBL, Mach3, Siemens 840D,
  Heidenhain, Waterjet/Laser**. Pick one from the "Machine post" dropdown in
  the G-Code dialog.
- **Make your own post**: edit `posts/fanuc.py`, or use **Edit Post...** in the
  G-Code dialog — every G-code line is a user-editable template
  (`{x} {y} {z} {f} {i} {j} {tool} {rpm} {wcs} {var:NAME} ...`) plus a
  `variables` block and boolean `options`. Save Post (.py) and it appears in
  the dropdown. Because posts are plain `.py` files, you can retarget output to
  a new controller on the installed `.exe` without rebuilding.

## Text as machinable geometry (stroke fonts)
Two text commands create **real, cuttable geometry** (single-line / engraving
centerlines) instead of a static label. Each asks for a start point, a height,
and the string (no in-command font picker):

- **TEXT** (`T`/`TEXT`/`DT`) — **general**: the original QCAD `.cxf` stroke
  font, drawn as a single pass of `Line` + `Arc` centerlines.
- **TEXTS** (`TEXTS`/`TS`) — **single-line / engraving** font: `Line` + `Arc`
  centerlines (ideal for V-bit engraving, lasers, plotters — one fast pass).
  Curves are **real arcs**, so G-code emits true `G02`/`G03` circular moves.

Each has its own ribbon icon in the **Annotate > Text** panel.

Glyph shapes come from a public-domain QCAD `.cxf` stroke font in `fonts/`
(`normal.cxf`). Drop in another `.cxf` and call `set_cxf_font(...)` to change
faces. Because the output is `LINE`/`ARC`, the G-code engine machines text
automatically — select the text entities and generate G-code like any other
geometry. See `fonts.md` for details. (The decorative `assets/fonts/Norase.otf`
display font is kept as a reference asset but is not wired into the commands —
it is an outline font, not a stroke font.)

## G-code: machine only the entities you pick
With 10000 lines in the drawing, you don't have to G-code them all. In the
G-Code Generator dialog:
- **Use current canvas selection** — uses whatever is already selected.
- **Pick entities on canvas...** — hides the dialog, you window/drag-select
  just the entities you want on the canvas, then press **Enter** (or Space) to
  resume the dialog with that selection. **Esc** cancels back to the dialog.
- **Select ALL geometry** — everything.

The selected subset is what gets toolpathed; text and point markers are still
emitted as comments, not cut.

## Workflow niceties
- **Repeat last command**: press **Enter** (or **Space**) on an empty command
  line to re-run the previous geometry command (AutoCAD-style). Dialog-only
  commands (open/save, G-code) are intentionally not auto-repeated.
- **Robust Undo/Redo**: `Ctrl+Z` / `Ctrl+Y` snapshot the full drawing
  including entities, layers, constraints and design variables, so every edit
  (draw, move, dimension-drive, constraint add) undoes cleanly in one step.


- Not a full AutoCAD replacement — no 3D solids, no true dynamic blocks, no annotative dimensions
- TRIM/EXTEND/BREAK are stubbed — geometry-level trim against arbitrary entities is the next
  chunk of work (non-trivial: needs a robust intersection engine)
- STRETCH currently moves the whole selection (vertex-level stretch not implemented)
- DWG uses ODA File Converter as a subprocess, not a native DWG parser (this is standard practice —
  true DWG read/write is only fully licensed to Autodesk + ODA members)

## Setup
```bash
pip install -r requirements.txt
python main.py
```

### DWG support
Install the free **ODA File Converter**:
https://www.opendesign.com/guestfiles/oda_file_converter
Once installed (default path detected automatically on Windows), Open/Save DWG works
transparently — the app converts DWG→DXF→DWG behind the scenes via subprocess.

## Compiling to EXE
```bash
pip install pyinstaller
pyinstaller pycad.spec
```
Output: `dist/PyCAD/PyCAD.exe`. Ship the whole `dist/PyCAD` folder (PyInstaller's `--onefile`
also works but is slower to start — swap `pycad.spec`'s COLLECT step if you want that instead).

## File map
- `entities.py` — internal geometry model (Line/Circle/Arc/LWPolyline/Text), independent of ezdxf
- `io_dxf.py` — DXF/DWG load & save
- `canvas.py` — QPainter canvas: transforms, rendering, mouse/keys, selection
- `commands.py` — generator-based command engine (AutoCAD prompt-style), ~30 real implementations
- `fonts.py` — stroke-font engine: parses QCAD `.cxf` files and renders single-line (Line+Arc engrave) + double-line (outline/cut) text as real geometry
- `command_table.py` — full alias table transcribed from the Shortcuts Guide PDF
- `gcode.py` — G-code engine, ported from `GCODEGEN_.lsp` (emits neutral toolpath events)
- `gcode_dialog.py` — G-code parameter dialog + live preview + post-processor picker/editor
- `constraints.py` — parametric engine: geometric/dimensional constraints, design variables, solver, auto-constrain
- `posts/` — pluggable post-processor package: `base.py` (BasePost "language") + one `.py` file per machine, auto-discovered
- `main.py` — main window, toolbar, command-line bar, menus

## Roadmap for filling out the remaining ~120 commands
Each alias in `command_table.py` maps to a full command name. To implement one:
1. Write a generator function in `commands.py` following the existing pattern
   (`yield Prompt(Prompt.POINT, "...")` / `Prompt.TEXT` / `Prompt.SELECTION`, end with `yield done(...)`)
2. Register it in the `COMMANDS` dict at the bottom of `commands.py`
That's the whole extension point — the canvas and command line already drive any generator
registered there.
