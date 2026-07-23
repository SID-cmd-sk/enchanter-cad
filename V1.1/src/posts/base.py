"""
posts/base.py
Base class for all PyCAD post-processors.

A post is a .py file in the posts/ folder that subclasses BasePost and sets:
    name, description, variables, options, templates

The default behavior turns the controller-neutral toolpath EVENTS (emitted by
gcode.py) into machine G-code using the templates.  Every step is also a
method you can override for full programmatic control (see process_events and
the per-event methods below).

Event placeholders available in templates:
    {x} {y} {z} {f} {i} {j} {r} {tool} {rpm} {wcs} {p} {name} {text}
    {code} {dnum}
and any variable you define in `variables`, referenced as {var:VARNAME},
e.g. {var:SAFE_Z} -> the post's SAFE_Z value.
"""

import math


class BasePost:
    # ---- metadata (override in subclass) ----
    name = "Unnamed Post"
    description = ""

    # ---- user-tweakable defaults (override in subclass) ----
    # `variables` are plain named values the templates/methods can reference.
    variables = {}
    # `options` are simple boolean/string toggles the processor reads.
    options = {
        "absolute": True,
        "metric": True,
        "use_i_j": True,
        "arc_clockwise": "G02",
        "arc_ccw": "G03",
        "comment_paren": True,
        "use_wcs": True,
        "line_numbers": False,
    }

    # ---- G-code templates (override in subclass) ----
    templates = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def var(self, key, default=0.0):
        return self.variables.get(key, default)

    def opt(self, key, default=None):
        return self.options.get(key, default)

    def _fmt(self, template, **kw):
        """Format a template, injecting post variables as {var:NAME}."""
        try:
            return template.format(**kw, var=self._var_resolver())
        except Exception:
            return template

    class _VarResolver:
        def __init__(self, post):
            self._post = post

        def __getitem__(self, key):
            return self._post.variables.get(key, 0.0)

    def _var_resolver(self):
        return self._VarResolver(self)

    # ------------------------------------------------------------------
    # Default event -> G-code mapping (override any method to customize)
    # ------------------------------------------------------------------
    def header(self, ctx):
        out = []
        out.append(self._fmt(self.templates.get("program_start", "%\n"),
                              name=ctx["name"]))
        out.append(self._fmt(self.templates.get("comment", "({text})\n"),
                              text="PyCAD post: " + self.name))
        return "".join(out)

    def footer(self, ctx):
        return self._fmt(self.templates.get("program_end", "M30\n%\n"))

    def wcs(self, code, ctx):
        if not self.opt("use_wcs", True):
            return ""
        return self._fmt(self.templates.get("wcs", "{wcs}\n"), wcs=code)

    def toolchange(self, num, ctx):
        return self._fmt(self.templates.get("toolchange", "T{tool}\n"),
                          tool=num)

    def spin_on(self, rpm, cw, ctx):
        return self._fmt(self.templates.get("spin_on", "M03 S{rpm:.0f}\n"),
                          rpm=rpm, cw=cw)

    def spin_off(self, ctx):
        return self._fmt(self.templates.get("spin_off", "M05\n"))

    def cool_on(self, ctx):
        return self._fmt(self.templates.get("cool_on", "M08\n"))

    def cool_off(self, ctx):
        return self._fmt(self.templates.get("cool_off", "M09\n"))

    def rapid(self, x, y, z, ctx):
        return self._fmt(self.templates.get("rapid", "G00 X{x:.3f} Y{y:.3f} Z{z:.3f}\n"),
                          x=x, y=y, z=z)

    def rapid_home(self, z, x, y, ctx):
        return self._fmt(self.templates.get("rapid_home",
                                            "G00 Z{z:.3f}\nG00 X{x:.3f} Y{y:.3f}\n"),
                          z=z, x=x, y=y)

    def plunge(self, z, f, ctx):
        return self._fmt(self.templates.get("plunge", "G01 Z{z:.3f} F{f:.0f}\n"),
                          z=z, f=f)

    def cut_linear(self, x, y, f, ctx):
        return self._fmt(self.templates.get("cut_linear",
                                            "G01 X{x:.3f} Y{y:.3f} F{f:.0f}\n"),
                          x=x, y=y, f=f)

    def cut_arc(self, x, y, i, j, f, cw, ctx):
        key = "cut_arc_cw" if cw else "cut_arc_ccw"
        return self._fmt(self.templates.get(key,
                                            "G02 X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{f:.3f}\n"),
                          x=x, y=y, i=i, j=j, f=f)

    def comp_on(self, code, dnum, ctx):
        return self._fmt(self.templates.get("comp_on", "{code} D{dnum}\n"),
                          code=code, dnum=dnum)

    def comp_off(self, ctx):
        return self._fmt(self.templates.get("comp_off", "G40\n"))

    def dwell(self, p, ctx):
        return self._fmt(self.templates.get("dwell", "G04 P{p:.2f}\n"), p=p)

    def comment(self, text, ctx):
        return self._fmt(self.templates.get("comment", "({text})\n"), text=text)

    # ------------------------------------------------------------------
    # Top-level driver: events -> text.  Override to fully rewrite output.
    # ------------------------------------------------------------------
    def process(self, events, ctx):
        out = []
        for ev in events:
            kind = ev[0]
            if kind == "PROGRAM_START":
                out.append(self.header(ctx))
            elif kind == "PROGRAM_END":
                out.append(self.footer(ctx))
            elif kind == "WCS":
                out.append(self.wcs(ev[1] if len(ev) > 1 else ctx.get("wcs", "G54"),
                                    ctx))
            elif kind == "TOOLCHANGE":
                out.append(self.toolchange(ev[1], ctx))
            elif kind == "SPIN_ON":
                cw = ev[2] if len(ev) > 2 else True
                out.append(self.spin_on(ev[1], cw, ctx))
            elif kind == "SPIN_OFF":
                out.append(self.spin_off(ctx))
            elif kind == "COOL_ON":
                out.append(self.cool_on(ctx))
            elif kind == "COOL_OFF":
                out.append(self.cool_off(ctx))
            elif kind == "RAPID":
                out.append(self.rapid(ev[1], ev[2], ev[3], ctx))
            elif kind == "PLUNGE":
                f = ev[2] if len(ev) > 2 else ctx.get("plungef", 200.0)
                out.append(self.plunge(ev[1], f, ctx))
            elif kind == "CUT":
                x, y, f = ev[1], ev[2], ev[3]
                i = ev[4] if len(ev) > 4 else 0.0
                j = ev[5] if len(ev) > 5 else 0.0
                if i or j:
                    cw = ev[6] if len(ev) > 6 else False
                    out.append(self.cut_arc(x, y, i, j, f, cw, ctx))
                else:
                    out.append(self.cut_linear(x, y, f, ctx))
            elif kind == "CUTARC":
                x, y, i, j, f, cw = ev[1], ev[2], ev[3], ev[4], ev[5], ev[6]
                out.append(self.cut_arc(x, y, i, j, f, cw, ctx))
            elif kind == "COMP_ON":
                out.append(self.comp_on(ev[1], ev[2], ctx))
            elif kind == "COMP_OFF":
                out.append(self.comp_off(ctx))
            elif kind == "DWELL":
                out.append(self.dwell(ev[1], ctx))
            elif kind == "COMMENT":
                out.append(self.comment(ev[1], ctx))
            elif kind == "RAPID_HOME":
                out.append(self.rapid_home(ev[1], ev[2], ev[3], ctx))
        return "".join(out)
