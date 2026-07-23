"""
constraints.py
Parametric / variational modeling engine for PyCAD (SolidWorks-style).

A Drawing can hold a set of CONSTRAINT objects plus DESIGN VARIABLES.  The
solver runs each time geometry is edited and snaps entities back onto the
constraints, exactly like a parametric CAD package:

  * Geometric constraints: COINCIDENT, HORIZONTAL, VERTICAL, PARALLEL,
    PERPENDICULAR, TANGENT, EQUAL, CONCENTRIC, MIDPOINT, COLLINEAR.
  * Dimensional constraints: DISTANCE (between two points/lines),
    RADIUS/DIAMETER (circle/arc), ANGLE (between two lines), plus driven
    "reference" dimensions.
  * Design variables: named parameters (e.g. "W=100", "D=25") that
    dimensional constraints can reference, so editing one value updates the
    whole sketch.

Auto-constrain (like SolidWorks "Fully Define Sketch" / inferencing): given a
selection, the engine infers likely geometric constraints from the current
geometry (e.g. two endpoints that touch -> COINCIDENT; a line that is nearly
horizontal -> HORIZONTAL) and adds them.

The solver is a simple iterative Gauss-Seidel relaxation over small residual
functions, which is robust for 2D sketch constraints and easy to reason about.
"""
import math
from entities import (Line, Circle, Arc, LWPolyline, Entity)


# --------------------------------------------------------------------------
# Design variables (the "parameters" of a parametric model)
# --------------------------------------------------------------------------

class Variable:
    """A named design parameter.  value is a float.  expr may later be
    evaluated (kept as a plain stored value for now)."""
    def __init__(self, name, value, desc=""):
        self.name = name
        self.value = float(value)
        self.desc = desc

    def __repr__(self):
        return f"Variable({self.name}={self.value:g})"


# --------------------------------------------------------------------------
# Constraint base
# --------------------------------------------------------------------------

class Constraint:
    KIND = "CONSTRAINT"

    def __init__(self, entities, driven=False):
        # list of entity objects the constraint references
        self.entities = list(entities)
        self.driven = driven   # driven = just measures, does not constrain
        self.value = None      # for dimensional constraints
        self.var = None        # optional Variable name this dimension uses
        self.selected = False
        self._id = None

    # ---- delegate helpers to fetch points on referenced entities ----
    def _point(self, ent, which):
        """Return a world point for (ent, which).  which in
        {'p1','p2','c','mid1','mid2'} etc."""
        if ent.kind == "LINE":
            return ent.p1 if which == "p1" else ent.p2
        if ent.kind == "CIRCLE":
            return ent.center
        if ent.kind == "ARC":
            if which == "c":
                return ent.center
            if which == "p1":
                return ent.start_point()
            if which == "p2":
                return ent.end_point()
        if ent.kind == "LWPOLYLINE":
            pts = [(v[0], v[1]) for v in ent.verts]
            if which == "p1":
                return pts[0]
            if which == "p2":
                return pts[-1]
        return (0.0, 0.0)

    def set_point(self, ent, which, x, y):
        if ent.kind == "LINE":
            if which == "p1":
                ent.p1 = (x, y)
            else:
                ent.p2 = (x, y)
        elif ent.kind == "CIRCLE":
            ent.center = (x, y)
        elif ent.kind == "ARC":
            if which == "c":
                ent.center = (x, y)
        elif ent.kind == "LWPOLYLINE":
            pts = list(ent.verts)
            if which == "p1":
                pts[0] = (x, y, pts[0][2])
            elif which == "p2":
                pts[-1] = (x, y, pts[-1][2])
            ent.verts = pts

    def residual(self, solver):
        """Return scalar error (0 when satisfied).  Override."""
        return 0.0

    def apply(self, solver, step=1.0):
        """Move referenced geometry to reduce the residual.  Override."""
        pass

    def description(self):
        return self.KIND


# --------------------------------------------------------------------------
# Geometric constraints
# --------------------------------------------------------------------------

class Coincident(Constraint):
    KIND = "COINCIDENT"
    def __init__(self, e1, w1, e2, w2):
        super().__init__([e1, e2])
        self.w1, self.w2 = w1, w2

    def residual(self, solver):
        a = self._point(self.entities[0], self.w1)
        b = self._point(self.entities[1], self.w2)
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def apply(self, solver, step=1.0):
        a = self._point(self.entities[0], self.w1)
        b = self._point(self.entities[1], self.w2)
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        # move both endpoints halfway toward the average
        self.set_point(self.entities[0], self.w1,
                       a[0] + (mx - a[0]) * step, a[1] + (my - a[1]) * step)
        self.set_point(self.entities[1], self.w2,
                       b[0] + (mx - b[0]) * step, b[1] + (my - b[1]) * step)

    def description(self):
        return f"Coincident {self.w1}-{self.w2}"


class Horizontal(Constraint):
    KIND = "HORIZONTAL"
    def __init__(self, ent, w1="p1", w2="p2"):
        super().__init__([ent])
        self.w1, self.w2 = w1, w2

    def residual(self, solver):
        a = self._point(self.entities[0], self.w1)
        b = self._point(self.entities[0], self.w2)
        return abs(a[1] - b[1])

    def apply(self, solver, step=1.0):
        a = self._point(self.entities[0], self.w1)
        b = self._point(self.entities[0], self.w2)
        my = (a[1] + b[1]) / 2.0
        self.set_point(self.entities[0], self.w1, a[0], a[1] + (my - a[1]) * step)
        self.set_point(self.entities[0], self.w2, b[0], b[1] + (my - b[1]) * step)

    def description(self):
        return "Horizontal"


class Vertical(Constraint):
    KIND = "VERTICAL"
    def __init__(self, ent, w1="p1", w2="p2"):
        super().__init__([ent])
        self.w1, self.w2 = w1, w2

    def residual(self, solver):
        a = self._point(self.entities[0], self.w1)
        b = self._point(self.entities[0], self.w2)
        return abs(a[0] - b[0])

    def apply(self, solver, step=1.0):
        a = self._point(self.entities[0], self.w1)
        b = self._point(self.entities[0], self.w2)
        mx = (a[0] + b[0]) / 2.0
        self.set_point(self.entities[0], self.w1, a[0] + (mx - a[0]) * step, a[1])
        self.set_point(self.entities[0], self.w2, b[0] + (mx - b[0]) * step, b[1])

    def description(self):
        return "Vertical"


class Parallel(Constraint):
    KIND = "PARALLEL"
    def __init__(self, e1, e2):
        super().__init__([e1, e2])

    def residual(self, solver):
        d1 = self._dir(self.entities[0])
        d2 = self._dir(self.entities[1])
        # sin of angle between -> 0 when parallel
        return abs(d1[0] * d2[1] - d1[1] * d2[0])

    def _dir(self, ent):
        a = self._point(ent, "p1"); b = self._point(ent, "p2")
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        return (dx / L, dy / L)

    def apply(self, solver, step=1.0):
        d1 = self._dir(self.entities[0])
        d2 = self._dir(self.entities[1])
        # rotate ent[1] endpoint slightly toward ent[0]'s direction about its p1
        a = self._point(self.entities[1], "p1")
        b = self._point(self.entities[1], "p2")
        ang = math.atan2(d1[1], d1[0]) - math.atan2(d2[1], d2[0])
        ang *= 0.5 * step
        c, s = math.cos(ang), math.sin(ang)
        dx, dy = b[0] - a[0], b[1] - a[1]
        nb = (a[0] + dx * c - dy * s, a[1] + dx * s + dy * c)
        self.set_point(self.entities[1], "p2", nb[0], nb[1])

    def description(self):
        return "Parallel"


class Perpendicular(Constraint):
    KIND = "PERPENDICULAR"
    def __init__(self, e1, e2):
        super().__init__([e1, e2])

    def residual(self, solver):
        a = self._point(self.entities[0], "p1"); b = self._point(self.entities[0], "p2")
        c = self._point(self.entities[1], "p1"); d = self._point(self.entities[1], "p2")
        u = (b[0] - a[0], b[1] - a[1]); v = (d[0] - c[0], d[1] - c[1])
        return abs(u[0] * v[0] + u[1] * v[1]) / ((math.hypot(*u) or 1) * (math.hypot(*v) or 1))

    def apply(self, solver, step=1.0):
        a = self._point(self.entities[0], "p1"); b = self._point(self.entities[0], "p2")
        u = (b[0] - a[0], b[1] - a[1]); ua = math.atan2(u[1], u[0])
        c = self._point(self.entities[1], "p1"); d = self._point(self.entities[1], "p2")
        v = (d[0] - c[0], d[1] - c[1]); va = math.atan2(v[1], v[0])
        # target: va = ua +/- 90deg
        target = ua + math.pi / 2.0
        diff = (target - va + math.pi) % (2 * math.pi) - math.pi
        diff *= 0.5 * step
        nc = math.cos(va + diff); ns = math.sin(va + diff)
        L = math.hypot(*v) or 1
        nd = (c[0] + L * nc, c[1] + L * ns)
        self.set_point(self.entities[1], "p2", nd[0], nd[1])

    def description(self):
        return "Perpendicular"


class Equal(Constraint):
    KIND = "EQUAL"
    def __init__(self, e1, e2):
        super().__init__([e1, e2])

    def residual(self, solver):
        l1 = self._len(self.entities[0]); l2 = self._len(self.entities[1])
        return abs(l1 - l2)

    def _len(self, ent):
        if ent.kind in ("LINE", "LWPOLYLINE"):
            a = self._point(ent, "p1"); b = self._point(ent, "p2")
            return math.hypot(b[0] - a[0], b[1] - a[1])
        if ent.kind in ("CIRCLE", "ARC"):
            return ent.radius
        return 0.0

    def apply(self, solver, step=1.0):
        l1 = self._len(self.entities[0]); l2 = self._len(self.entities[1])
        target = (l1 + l2) / 2.0
        for ent in self.entities:
            if ent.kind in ("CIRCLE", "ARC"):
                ent.radius += (target - ent.radius) * step
            else:
                a = self._point(ent, "p1"); b = self._point(ent, "p2")
                dx, dy = b[0] - a[0], b[1] - a[1]
                L = math.hypot(dx, dy) or 1
                nx, ny = dx / L * target, dy / L * target
                self.set_point(ent, "p2", a[0] + nx, a[1] + ny)

    def description(self):
        return "Equal length/radius"


class Concentric(Constraint):
    KIND = "CONCENTRIC"
    def __init__(self, e1, e2):
        super().__init__([e1, e2])

    def residual(self, solver):
        a = self._point(self.entities[0], "c"); b = self._point(self.entities[1], "c")
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def apply(self, solver, step=1.0):
        a = self._point(self.entities[0], "c"); b = self._point(self.entities[1], "c")
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        self.set_point(self.entities[0], "c", a[0] + (mx - a[0]) * step, a[1] + (my - a[1]) * step)
        self.set_point(self.entities[1], "c", b[0] + (mx - b[0]) * step, b[1] + (my - b[1]) * step)

    def description(self):
        return "Concentric"


class Tangent(Constraint):
    KIND = "TANGENT"
    def __init__(self, e1, e2):
        super().__init__([e1, e2])

    def residual(self, solver):
        # line vs circle/arc: distance(center, line) - radius
        line = None; circ = None
        for e in self.entities:
            if e.kind == "LINE":
                line = e
            elif e.kind in ("CIRCLE", "ARC"):
                circ = e
        if line is None or circ is None:
            return 0.0
        a = line.p1; b = line.p2
        c = circ.center
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        d = abs((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / L
        return abs(d - circ.radius)

    def apply(self, solver, step=1.0):
        line = None; circ = None
        for e in self.entities:
            if e.kind == "LINE":
                line = e
            elif e.kind in ("CIRCLE", "ARC"):
                circ = e
        if line is None or circ is None:
            return
        a = line.p1; b = line.p2
        c = circ.center
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        # unit normal to line
        nx, ny = -dy / L, dx / L
        d = ((c[0] - a[0]) * nx + (c[1] - a[1]) * ny)
        # move circle center along normal so distance == radius
        circ.center = (c[0] + (circ.radius - abs(d)) * math.copysign(1, d) * nx * step,
                       c[1] + (circ.radius - abs(d)) * math.copysign(1, d) * ny * step)

    def description(self):
        return "Tangent"


class Midpoint(Constraint):
    KIND = "MIDPOINT"
    def __init__(self, line_ent, pt_ent, pt_which="p1"):
        super().__init__([line_ent, pt_ent])
        self.pt_which = pt_which

    def residual(self, solver):
        a = self._point(self.entities[0], "p1"); b = self._point(self.entities[0], "p2")
        m = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        p = self._point(self.entities[1], self.pt_which)
        return math.hypot(m[0] - p[0], m[1] - p[1])

    def apply(self, solver, step=1.0):
        a = self._point(self.entities[0], "p1"); b = self._point(self.entities[0], "p2")
        m = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        p = self._point(self.entities[1], self.pt_which)
        self.set_point(self.entities[1], self.pt_which,
                       p[0] + (m[0] - p[0]) * step, p[1] + (m[1] - p[1]) * step)

    def description(self):
        return "Midpoint"


# --------------------------------------------------------------------------
# Dimensional constraints
# --------------------------------------------------------------------------

class DistanceDim(Constraint):
    KIND = "DISTANCE"
    def __init__(self, e1, w1, e2, w2, value=None, var=None):
        super().__init__([e1, e2], driven=(value is None and var is None))
        self.w1, self.w2 = w1, w2
        self.value = value
        self.var = var

    def target(self, vars_):
        if self.var and self.var in vars_:
            return vars_[self.var].value
        return self.value

    def residual(self, solver):
        a = self._point(self.entities[0], self.w1)
        b = self._point(self.entities[1], self.w2)
        cur = math.hypot(a[0] - b[0], a[1] - b[1])
        t = self.target(solver.vars) if not self.driven else cur
        return cur - t if t is not None else 0.0

    def apply(self, solver, step=1.0):
        a = self._point(self.entities[0], self.w1)
        b = self._point(self.entities[1], self.w2)
        cur = math.hypot(a[0] - b[0], a[1] - b[1]) or 1e-9
        t = self.target(solver.vars)
        if t is None:
            return
        f = t / cur
        # scale vector from a to b; keep a fixed, move b
        nb = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        self.set_point(self.entities[1], self.w2,
                       b[0] + (nb[0] - b[0]) * step, b[1] + (nb[1] - b[1]) * step)

    def description(self):
        t = self.target({}) if not self.var else self.var
        return f"Distance = {t:g}" if t is not None else "Distance (driven)"


class RadiusDim(Constraint):
    KIND = "RADIUS"
    def __init__(self, ent, value=None, var=None, diameter=False):
        super().__init__([ent], driven=(value is None and var is None))
        self.value = value
        self.var = var
        self.diameter = diameter

    def target(self, vars_):
        """Radius target (already accounts for diameter -> value/2)."""
        if self.var and self.var in vars_:
            v = vars_[self.var].value
            return v if not self.diameter else v / 2.0
        if self.value is None:
            return None
        return self.value if not self.diameter else self.value / 2.0

    def residual(self, solver):
        cur = self.entities[0].radius
        if self.driven:
            return 0.0
        t = self.target(solver.vars)
        if t is None:
            return 0.0
        return cur - t

    def apply(self, solver, step=1.0):
        t = self.target(solver.vars)
        if t is None:
            return
        e = self.entities[0]
        e.radius += (t - e.radius) * step

    def description(self):
        t = self.target({}) if not self.var else self.var
        if t is None:
            return "Radius (driven)"
        return f"{'Diameter' if self.diameter else 'Radius'} = {t:g}"


class AngleDim(Constraint):
    KIND = "ANGLE"
    def __init__(self, e1, e2, value=None, var=None):
        super().__init__([e1, e2], driven=(value is None and var is None))
        self.value = value
        self.var = var

    def target(self, vars_):
        if self.var and self.var in vars_:
            return math.radians(vars_[self.var].value)
        return math.radians(self.value) if self.value is not None else None

    def residual(self, solver):
        a1 = self._ang(self.entities[0]); a2 = self._ang(self.entities[1])
        cur = abs((a2 - a1 + math.pi) % (2 * math.pi) - math.pi)
        t = self.target(solver.vars)
        return cur - t if t is not None else 0.0

    def _ang(self, ent):
        a = self._point(ent, "p1"); b = self._point(ent, "p2")
        return math.atan2(b[1] - a[1], b[0] - a[0])

    def apply(self, solver, step=1.0):
        t = self.target(solver.vars)
        if t is None:
            return
        a1 = self._ang(self.entities[0]); a2 = self._ang(self.entities[1])
        cur = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        diff = (t - cur) * 0.5 * step
        c = self._point(self.entities[1], "p1")
        b = self._point(self.entities[1], "p2")
        va = math.atan2(b[1] - c[1], b[0] - c[0]) + diff
        L = math.hypot(b[0] - c[0], b[1] - c[1]) or 1
        self.set_point(self.entities[1], "p2",
                       c[0] + L * math.cos(va), c[1] + L * math.sin(va))

    def description(self):
        t = self.target({}) if not self.var else self.var
        return f"Angle = {t:g} deg" if t is not None else "Angle (driven)"


# --------------------------------------------------------------------------
# Solver
# --------------------------------------------------------------------------

class Solver:
    """Gauss-Seidel relaxation solver over the constraint list."""

    def __init__(self, constraints, variables):
        self.constraints = constraints
        self.vars = variables  # dict name -> Variable

    def solve(self, iterations=200, tol=1e-6):
        for _ in range(iterations):
            max_res = 0.0
            for c in self.constraints:
                if c.driven:
                    continue
                try:
                    r = abs(c.residual(self))
                except Exception:
                    r = 0.0
                max_res = max(max_res, r)
                try:
                    c.apply(self, step=0.5)
                except Exception:
                    pass
            if max_res < tol:
                break
        return max_res


# --------------------------------------------------------------------------
# Auto-constrain engine (SolidWorks-style inference)
# --------------------------------------------------------------------------

def autoconstrain(entities, tol=1e-3):
    """Given a list of entities, infer a reasonable set of geometric
    constraints (and dimensional ones where a clear value exists) and return
    them.  Mirrors how SolidWorks infers relations as you sketch.

    Heuristics:
      * Endpoints of two entities that coincide (within tol) -> COINCIDENT.
      * Lines within eps of horizontal/vertical -> HORIZONTAL / VERTICAL.
      * Circles/arcs sharing a center -> CONCENTRIC.
      * A line nearly parallel/perpendicular to another -> PARALLEL/PERP.
      * Two equal-length lines / equal-radius circles -> EQUAL.
    """
    cons = []
    lines = [e for e in entities if e.kind == "LINE"]
    circles = [e for e in entities if e.kind in ("CIRCLE", "ARC")]
    eps = 0.02  # angular tolerance (radians) for H/V/parallel/perp

    def near(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1]) < tol

    # coincident endpoints
    pts = []  # (entity, which, point)
    for e in entities:
        if e.kind == "LINE":
            pts.append((e, "p1", e.p1)); pts.append((e, "p2", e.p2))
        elif e.kind == "LWPOLYLINE":
            pts.append((e, "p1", (e.verts[0][0], e.verts[0][1])))
            pts.append((e, "p2", (e.verts[-1][0], e.verts[-1][1])))
        elif e.kind in ("CIRCLE", "ARC"):
            pts.append((e, "c", e.center))
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            if near(pts[i][2], pts[j][2]):
                cons.append(Coincident(pts[i][0], pts[i][1], pts[j][0], pts[j][1]))

    # horizontal / vertical lines
    for e in lines:
        dx = e.p2[0] - e.p1[0]; dy = e.p2[1] - e.p1[1]
        if abs(dy) < eps * max(abs(dx), 1e-9) and abs(dx) > 1e-6:
            cons.append(Horizontal(e))
        if abs(dx) < eps * max(abs(dy), 1e-9) and abs(dy) > 1e-6:
            cons.append(Vertical(e))

    # concentric circles/arcs
    for i in range(len(circles)):
        for j in range(i + 1, len(circles)):
            if near(circles[i].center, circles[j].center):
                cons.append(Concentric(circles[i], circles[j]))

    # parallel / perpendicular line pairs
    def _axis_aligned(e):
        dx = e.p2[0] - e.p1[0]; dy = e.p2[1] - e.p1[1]
        return abs(dx) < eps * max(abs(dy), 1e-9) or abs(dy) < eps * max(abs(dx), 1e-9)

    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            # H/V constraints already fix angles of axis-aligned lines; adding
            # parallel/perpendicular between them is redundant and fights the
            # solver, so skip when both are axis-aligned.
            if _axis_aligned(lines[i]) and _axis_aligned(lines[j]):
                continue
            a = (lines[i].p2[0] - lines[i].p1[0], lines[i].p2[1] - lines[i].p1[1])
            b = (lines[j].p2[0] - lines[j].p1[0], lines[j].p2[1] - lines[j].p1[1])
            la = math.hypot(*a) or 1; lb = math.hypot(*b) or 1
            cross = abs(a[0] * b[1] - a[1] * b[0]) / (la * lb)
            dot = abs(a[0] * b[0] + a[1] * b[1]) / (la * lb)
            if cross < eps and dot > 0.5:
                cons.append(Parallel(lines[i], lines[j]))
            elif dot < eps and cross > 0.5:
                cons.append(Perpendicular(lines[i], lines[j]))

    # equal length / radius
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            l1 = math.hypot(lines[i].p2[0] - lines[i].p1[0], lines[i].p2[1] - lines[i].p1[1])
            l2 = math.hypot(lines[j].p2[0] - lines[j].p1[0], lines[j].p2[1] - lines[j].p1[1])
            if abs(l1 - l2) < tol and l1 > 1e-6:
                cons.append(Equal(lines[i], lines[j]))
    for i in range(len(circles)):
        for j in range(i + 1, len(circles)):
            if abs(circles[i].radius - circles[j].radius) < tol:
                cons.append(Equal(circles[i], circles[j]))

    return cons


# --------------------------------------------------------------------------
# Registry / factory used by the command + UI layer
# --------------------------------------------------------------------------

CONSTRAINT_TYPES = {
    "COINCIDENT": Coincident,
    "HORIZONTAL": Horizontal,
    "VERTICAL": Vertical,
    "PARALLEL": Parallel,
    "PERPENDICULAR": Perpendicular,
    "EQUAL": Equal,
    "CONCENTRIC": Concentric,
    "TANGENT": Tangent,
    "MIDPOINT": Midpoint,
    "DISTANCE": DistanceDim,
    "RADIUS": RadiusDim,
    "DIAMETER": RadiusDim,
    "ANGLE": AngleDim,
}


# --------------------------------------------------------------------------
# Live constraint INFERENCE (SolidWorks-style on-hover / on-drag)
# --------------------------------------------------------------------------
# When the user places or drags a point near existing geometry, we work out
# the most likely relation and (a) snap the cursor to it and (b) propose the
# constraint to create.  A small glyph is shown by the canvas so the user
# sees what relation will be applied before they click.

def _entity_anchor_points(e):
    """Yield (point, which) anchors of an entity used for coincident snapping."""
    if e.kind == "LINE":
        yield (e.p1, "p1"); yield (e.p2, "p2")
    elif e.kind == "LWPOLYLINE":
        n = len(e.verts)
        for i in range(n):
            yield ((e.verts[i][0], e.verts[i][1]), ("p1" if i == 0 else "p2") if (i == 0 or i == n - 1) else f"v{i}")
    elif e.kind in ("CIRCLE", "ARC"):
        yield (e.center, "c")
        if e.kind == "CIRCLE":
            for k in range(4):
                a = math.pi / 2 * k
                yield ((e.center[0] + e.radius * math.cos(a),
                        e.center[1] + e.radius * math.sin(a)), "q")
        else:
            yield (e.start_point(), "p1"); yield (e.end_point(), "p2")
    elif e.kind == "POINT":
        yield (e.pos, "p1")


def infer_point_constraint(wx, wy, entities, moving_ent=None, tol=8.0):
    """Find the best geometric relation for a point (wx, wy) near `entities`.

    Returns (glyph, snap_point, constraint_factory) or None.
      glyph: one of 'COINCIDENT','TANGENT','PERPENDICULAR','PARALLEL',
             'HORIZONTAL','VERTICAL'
      constraint_factory: callable(other_ent, which, ...) -> Constraint, or
             None when the relation needs no new constraint (e.g. H/V of the
             moving line itself).
    moving_ent: the entity currently being created/edited (ignored as a target).
    """
    best = None  # (priority, dist, glyph, snap, factory)

    def consider(priority, dist, glyph, snap, factory):
        nonlocal best
        if best is None or priority < best[0] or (priority == best[0] and dist < best[1]):
            best = (priority, dist, glyph, snap, factory)

    # 1) COINCIDENT to an anchor point of another entity (highest priority)
    for e in entities:
        if e is moving_ent:
            continue
        for (pt, which) in _entity_anchor_points(e):
            d = math.hypot(pt[0] - wx, pt[1] - wy)
            if d < tol:
                factory = lambda other=e, w=which: Coincident(moving_ent, "p1", other, w) if moving_ent else Coincident(other, w, other, w)
                consider(0, d, "COINCIDENT", pt, factory)

    # 2) TANGENT to a circle/arc (snap point onto boundary)
    for e in entities:
        if e is moving_ent or e.kind not in ("CIRCLE", "ARC"):
            continue
        dx, dy = wx - e.center[0], wy - e.center[1]
        L = math.hypot(dx, dy) or 1e-9
        if abs(L - e.radius) < tol:
            bx, by = e.center[0] + e.radius * dx / L, e.center[1] + e.radius * dy / L
            factory = lambda other=e: Tangent(moving_ent, other) if moving_ent else Tangent(other, other)
            consider(1, abs(L - e.radius), "TANGENT", (bx, by), factory)

    # 3) PERPENDICULAR / PARALLEL to a nearby line
    for e in entities:
        if e is moving_ent or e.kind != "LINE":
            continue
        a = e.p1; b = e.p2
        ux, uy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(ux, uy) or 1e-9
        nx, ny = -uy / L, ux / L
        dist_line = abs((wx - a[0]) * ny + (wy - a[1]) * nx)
        if dist_line < tol:
            t = ((wx - a[0]) * ux + (wy - a[1]) * uy) / (L * L)
            proj = (a[0] + t * ux, a[1] + t * uy)
            dirx, diry = wx - proj[0], wy - proj[1]
            cross = abs(dirx * uy - diry * ux) / (L * (math.hypot(dirx, diry) or 1))
            if cross > 0.5:
                factory = lambda other=e: Perpendicular(moving_ent, other) if moving_ent else Perpendicular(other, other)
                consider(2, dist_line, "PERPENDICULAR", proj, factory)
            else:
                factory = lambda other=e: Parallel(moving_ent, other) if moving_ent else Parallel(other, other)
                consider(3, dist_line, "PARALLEL", proj, factory)

    if best is None:
        return None
    _, dist, glyph, snap, factory = best
    return (glyph, snap, factory)


def infer_line_relation(ent, entities, tol=8.0):
    """For a line being drawn, check if its shape implies HORIZONTAL/VERTICAL
    (used to show a glyph and constrain the line itself)."""
    dx = ent.p2[0] - ent.p1[0]; dy = ent.p2[1] - ent.p1[1]
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return None
    if abs(dy) < 0.05 * max(abs(dx), 1e-6):
        return ("HORIZONTAL", lambda e=ent: Horizontal(e))
    if abs(dx) < 0.05 * max(abs(dy), 1e-6):
        return ("VERTICAL", lambda e=ent: Vertical(e))
    return None


def auto_connect_points(p1, p2, drawing, tol=1e-3):
    """After creating a LINE p1->p2, add COINCIDENT constraints to any existing
    entity endpoint/mid/center the line's endpoints land on.  Mirrors 'draw a
    line that touches another -> auto connected'."""
    added = 0
    line = None
    for e in reversed(drawing.entities):
        if e.kind == "LINE":
            line = e; break
    if line is None:
        return 0
    for pt, which in ((p1, "p1"), (p2, "p2")):
        for e in drawing.entities:
            if e is line:
                continue
            for (apt, aw) in _entity_anchor_points(e):
                if math.hypot(apt[0] - pt[0], apt[1] - pt[1]) < tol:
                    drawing.add_constraint(Coincident(line, which, e, aw))
                    added += 1
                    break
    return added

