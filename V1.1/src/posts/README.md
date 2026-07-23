# PyCAD Post-Processors (Machine Posts)

Every CNC machine / controller speaks slightly different G-code. PyCAD keeps
all of that machine-specific syntax in **post files** so the geometry engine
(`gcode.py`) never has to know about Fanuc vs Haas vs Siemens.

## The big idea

- **One machine = one `.py` file** in the `posts/` folder.
- PyCAD **auto-discovers** every `.py` post. Drop in 1 file → 1 post in the
  dropdown. Drop in 20 files → 20 posts. No central list, no JSON, no rebuild.
- Because posts are plain Python files loaded at runtime, you can edit or add
  a machine post on the **installed .exe** without recompiling anything. Just
  edit the `.py` file in the `posts/` folder next to the program and restart.

This is the equivalent of SolidCAM's GPP / machine definition files, but kept
simple and human-editable.

## Where the files live

```
cadapp/
  posts/
    __init__.py     # discovery + compatibility shim (don't edit)
    base.py         # BasePost class - the post "language" (don't edit)
    fanuc.py        # one machine
    haas.py         # one machine
    linuxcnc.py     # one machine
    grbl.py         # one machine
    mach3.py        # one machine
    siemens.py      # one machine
    heidenhain.py   # one machine
    waterjet.py     # one machine
    MyMachine.py    # <- add your own here
```

You can also use **Tools → G-Code Generator → Machine post → Edit Post** to
edit templates/variables/options in a dialog and **Save Post (.py)**, which
writes a new `.py` file into the same folder automatically.

## Anatomy of a post file

Here is the complete `fanuc.py` (every post looks like this):

```python
"""Fanuc (generic) post - the de-facto ISO G-code standard."""
from posts.base import BasePost


class Post(BasePost):
    name = "Fanuc (generic)"                 # shown in the post dropdown
    description = "Fanuc-style ISO G-code, the de-facto standard."

    # variables: named values you can reference in templates or methods
    variables = {"SAFE_Z": 10.0, "PARK_X": 0.0, "PARK_Y": 0.0}

    # options: simple toggles the processor reads
    options = {
        "absolute": True, "metric": True, "use_i_j": True,
        "arc_clockwise": "G02", "arc_ccw": "G03",
        "comment_paren": True, "leading_zero": False,
        "subroutines": False, "line_numbers": False, "use_wcs": True,
    }

    # templates: Python str.format() strings, one per toolpath event
    templates = {
        "program_start": "%\n(--- {name} ---)\nG21 G90 G17 G94\n",
        "wcs": "{wcs}\n",
        "toolchange": "T{tool} M06\n",
        "spin_on": "M03 S{rpm:.0f}\n",
        "cool_on": "M08\n",
        "cool_off": "M09\n",
        "rapid": "G00 X{x:.3f} Y{y:.3f} Z{z:.3f}\n",
        "plunge": "G01 Z{z:.3f} F{f:.0f}\n",
        "cut_linear": "G01 X{x:.3f} Y{y:.3f} F{f:.0f}\n",
        "cut_arc_cw": "G02 X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{f:.3f}\n",
        "cut_arc_ccw": "G03 X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{f:.3f}\n",
        "comp_on": "{code} D{dnum}\n",
        "comp_off": "G40\n",
        "dwell": "G04 P{p:.2f}\n",
        "spin_off": "M05\n",
        "rapid_home": "G00 Z{z:.3f}\nG00 X{x:.3f} Y{y:.3f}\n",
        "program_end": "M30\n%\n",
        "comment": "({text})\n",
    }
```

That's it. The class **must** be named `Post` and **must** subclass
`BasePost`. Everything else is optional (it falls back to defaults).

## Template placeholders

Inside any template string you can use these `{...}` placeholders:

| Placeholder   | Meaning                                    |
|---------------|--------------------------------------------|
| `{x}` `{y}` `{z}` | X / Y / Z position (mm)                 |
| `{f}`         | feed rate                                  |
| `{i}` `{j}`   | arc center offset (I/J words)              |
| `{r}`         | radius                                     |
| `{tool}`      | tool number                                |
| `{rpm}`       | spindle speed                             |
| `{wcs}`       | work coordinate system (e.g. `G54`)        |
| `{p}`         | dwell time (seconds)                       |
| `{name}`      | program / job name                         |
| `{text}`      | comment text                               |
| `{code}`      | cutter-comp code (`G41`/`G42`)             |
| `{dnum}`      | cutter-comp register number               |
| `{var:NAME}`  | a value from your `variables` block (e.g. `{var:SAFE_Z}`) |

The standard template keys are:

`program_start`, `wcs`, `toolchange`, `spin_on`, `cool_on`, `cool_off`,
`rapid`, `plunge`, `cut_linear`, `cut_arc_cw`, `cut_arc_ccw`, `comp_on`,
`comp_off`, `dwell`, `spin_off`, `rapid_home`, `program_end`, `comment`.

If a key is missing, PyCAD uses a sensible ISO default for that line, so you
only override the lines your machine does differently.

## The `variables` block

`variables` is a dict of named numbers. They are handy for machine constants
(SAFE_Z, park position, coolant codes, etc.) and are inserted into templates
with `{var:NAME}`. Example: set `"SAFE_Z": 25.0` and reference
`G00 Z{var:SAFE_Z}` in your `rapid_home` template.

## The `options` block

Simple toggles the engine reads:

- `absolute` (G90 vs G91), `metric` (G21 vs G20)
- `use_i_j` (emit I/J arc words vs R)
- `arc_clockwise` / `arc_ccw` (the G-words your controller uses, e.g. `G02`/`G03`)
- `comment_paren` (use `(...)` vs `; ...` comments)
- `use_wcs` (emit WCS line at all)

## Going further: override methods instead of templates

If string templates aren't enough (conditional logic, subroutines, custom
pecking cycles), override the matching method on your `Post` class. Each
method receives `(self, ctx)` and returns a string. Examples:

```python
def header(self, ctx):
    return "%\nO1000 (" + ctx["name"] + ")\nG21 G90\n"

def cut_arc(self, x, y, i, j, f, cw, ctx):
    g = self.opt("arc_ccw") if not cw else self.opt("arc_clockwise")
    return f"{g} X{x:.3f} Y{y:.3f} R{math.hypot(i, j):.3f} F{f:.0f}\n"
```

The full list of overridable methods lives in `posts/base.py`:
`header`, `footer`, `wcs`, `toolchange`, `spin_on`, `spin_off`, `cool_on`,
`cool_off`, `rapid`, `rapid_home`, `plunge`, `cut_linear`, `cut_arc`,
`comp_on`, `comp_off`, `dwell`, `comment`, and the top-level `process(events, ctx)`.

## How PyCAD turns geometry into your machine's G-code

1. `gcode.py` converts the selected geometry into **controller-neutral
   toolpath events** (RAPID, PLUNGE, CUT, CUTARC, COMP_ON, DWELL, ...).
2. The selected `Post` walks those events and fills in its templates
   (or calls its override methods), producing the final text.
3. The post dropdown in the G-Code Generator dialog picks which `Post` runs.

Because step 1 is shared, switching machines is just switching posts - the
same drawing produces Fanuc, Haas, Siemens, or your custom controller output.

## Adding your own machine (step by step)

1. Copy `posts/fanuc.py` to `posts/MyMill.py`.
2. Change `name`, `description`, and edit the `templates` to match your
   controller's syntax.
3. Save the file. Restart PyCAD (or it auto-loads on next launch).
4. Your machine now appears in the post dropdown.

No recompile, no JSON, no registry entry. Done.
