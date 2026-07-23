"""
entities.py
Internal geometry model used by the CAD engine. Kept independent of ezdxf
so the canvas/command layer never touches DXF structures directly -
io_dxf.py is the only place that translates to/from ezdxf.
"""
import math
import uuid


def new_id():
    return uuid.uuid4().hex[:8]


class Entity:
    """Base class. All entities live in world (drawing) coordinates, mm."""
    kind = "ENTITY"

    def __init__(self, layer="0", color=None):
        self.id = new_id()
        self.layer = layer
        self.color = color  # None = ByLayer
        self.selected = False

    def bbox(self):
        raise NotImplementedError

    def translate(self, dx, dy):
        raise NotImplementedError

    def rotate(self, cx, cy, angle_rad):
        raise NotImplementedError

    def scale(self, cx, cy, factor):
        raise NotImplementedError

    def mirror(self, p1, p2):
        raise NotImplementedError

    def clone(self):
        raise NotImplementedError

    def to_polyline_points(self, seg_len=1.0):
        """Flatten entity to a list of (x,y) points for G-code / trim / etc."""
        raise NotImplementedError


def _rot_pt(x, y, cx, cy, ang):
    dx, dy = x - cx, y - cy
    c, s = math.cos(ang), math.sin(ang)
    return (cx + dx * c - dy * s, cy + dx * s + dy * c)


def _mirror_pt(x, y, p1, p2):
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return (x, y)
    a = (dx * dx - dy * dy) / (dx * dx + dy * dy)
    b = 2 * dx * dy / (dx * dx + dy * dy)
    xn = a * (x - x1) + b * (y - y1) + x1
    yn = b * (x - x1) - a * (y - y1) + y1
    return (xn, yn)


class Line(Entity):
    kind = "LINE"

    def __init__(self, p1, p2, **kw):
        super().__init__(**kw)
        self.p1 = tuple(p1)
        self.p2 = tuple(p2)

    def bbox(self):
        xs = [self.p1[0], self.p2[0]]
        ys = [self.p1[1], self.p2[1]]
        return (min(xs), min(ys), max(xs), max(ys))

    def translate(self, dx, dy):
        self.p1 = (self.p1[0] + dx, self.p1[1] + dy)
        self.p2 = (self.p2[0] + dx, self.p2[1] + dy)

    def rotate(self, cx, cy, ang):
        self.p1 = _rot_pt(*self.p1, cx, cy, ang)
        self.p2 = _rot_pt(*self.p2, cx, cy, ang)

    def scale(self, cx, cy, f):
        self.p1 = (cx + (self.p1[0] - cx) * f, cy + (self.p1[1] - cy) * f)
        self.p2 = (cx + (self.p2[0] - cx) * f, cy + (self.p2[1] - cy) * f)

    def mirror(self, p1, p2):
        self.p1 = _mirror_pt(*self.p1, p1, p2)
        self.p2 = _mirror_pt(*self.p2, p1, p2)

    def clone(self):
        return Line(self.p1, self.p2, layer=self.layer, color=self.color)

    def to_polyline_points(self, seg_len=1.0):
        return [self.p1, self.p2]

    def length(self):
        return math.hypot(self.p2[0] - self.p1[0], self.p2[1] - self.p1[1])


class Circle(Entity):
    kind = "CIRCLE"

    def __init__(self, center, radius, **kw):
        super().__init__(**kw)
        self.center = tuple(center)
        self.radius = radius

    def bbox(self):
        cx, cy = self.center
        r = self.radius
        return (cx - r, cy - r, cx + r, cy + r)

    def translate(self, dx, dy):
        self.center = (self.center[0] + dx, self.center[1] + dy)

    def rotate(self, cx, cy, ang):
        self.center = _rot_pt(*self.center, cx, cy, ang)

    def scale(self, cx, cy, f):
        self.center = (cx + (self.center[0] - cx) * f, cy + (self.center[1] - cy) * f)
        self.radius *= abs(f)

    def mirror(self, p1, p2):
        self.center = _mirror_pt(*self.center, p1, p2)

    def clone(self):
        return Circle(self.center, self.radius, layer=self.layer, color=self.color)

    def to_polyline_points(self, seg_len=1.0):
        n = max(16, int((2 * math.pi * self.radius) / max(seg_len, 0.05)))
        cx, cy = self.center
        pts = []
        for i in range(n + 1):
            a = 2 * math.pi * i / n
            pts.append((cx + self.radius * math.cos(a), cy + self.radius * math.sin(a)))
        return pts


class Arc(Entity):
    kind = "ARC"

    def __init__(self, center, radius, start_ang, end_ang, **kw):
        """Angles in radians, CCW from start_ang to end_ang."""
        super().__init__(**kw)
        self.center = tuple(center)
        self.radius = radius
        self.start_ang = start_ang
        self.end_ang = end_ang

    def bbox(self):
        pts = self.to_polyline_points(seg_len=self.radius / 20 or 0.5)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def translate(self, dx, dy):
        self.center = (self.center[0] + dx, self.center[1] + dy)

    def rotate(self, cx, cy, ang):
        self.center = _rot_pt(*self.center, cx, cy, ang)
        self.start_ang += ang
        self.end_ang += ang

    def scale(self, cx, cy, f):
        self.center = (cx + (self.center[0] - cx) * f, cy + (self.center[1] - cy) * f)
        self.radius *= abs(f)

    def mirror(self, p1, p2):
        self.center = _mirror_pt(*self.center, p1, p2)
        # mirroring reverses arc direction
        self.start_ang, self.end_ang = -self.end_ang, -self.start_ang

    def clone(self):
        return Arc(self.center, self.radius, self.start_ang, self.end_ang,
                    layer=self.layer, color=self.color)

    def to_polyline_points(self, seg_len=1.0):
        sweep = self.end_ang - self.start_ang
        while sweep <= 0:
            sweep += 2 * math.pi
        n = max(8, int((sweep * self.radius) / max(seg_len, 0.05)))
        cx, cy = self.center
        pts = []
        for i in range(n + 1):
            a = self.start_ang + sweep * i / n
            pts.append((cx + self.radius * math.cos(a), cy + self.radius * math.sin(a)))
        return pts

    def start_point(self):
        return self.to_polyline_points()[0]

    def end_point(self):
        return self.to_polyline_points()[-1]


class LWPolyline(Entity):
    kind = "LWPOLYLINE"

    def __init__(self, verts, closed=False, **kw):
        """verts: list of (x, y, bulge) tuples. bulge=0 -> straight segment."""
        super().__init__(**kw)
        self.verts = [tuple(v) if len(v) == 3 else (v[0], v[1], 0.0) for v in verts]
        self.closed = closed

    def bbox(self):
        pts = self.to_polyline_points(seg_len=1.0)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def translate(self, dx, dy):
        self.verts = [(x + dx, y + dy, b) for x, y, b in self.verts]

    def rotate(self, cx, cy, ang):
        self.verts = [(*_rot_pt(x, y, cx, cy, ang), b) for x, y, b in self.verts]

    def scale(self, cx, cy, f):
        self.verts = [(cx + (x - cx) * f, cy + (y - cy) * f, b) for x, y, b in self.verts]

    def mirror(self, p1, p2):
        self.verts = [(*_mirror_pt(x, y, p1, p2), -b) for x, y, b in self.verts]
        self.verts.reverse()

    def clone(self):
        return LWPolyline(list(self.verts), closed=self.closed, layer=self.layer, color=self.color)

    def to_polyline_points(self, seg_len=1.0):
        pts = []
        n = len(self.verts)
        rng = range(n) if self.closed else range(n - 1)
        for i in rng:
            x1, y1, b = self.verts[i]
            x2, y2, _ = self.verts[(i + 1) % n]
            if abs(b) < 1e-9:
                seg = [(x1, y1), (x2, y2)]
            else:
                seg = _bulge_to_points((x1, y1), (x2, y2), b, seg_len)
            if pts and pts[-1] == seg[0]:
                pts.extend(seg[1:])
            else:
                pts.extend(seg)
        return pts


def _bulge_to_points(p1, p2, bulge, seg_len):
    d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if d < 1e-9:
        return [p1, p2]
    theta = 4 * math.atan(bulge)
    r = (d * 0.5) / math.sin(theta / 2.0)
    mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    ux, uy = (p2[0] - p1[0]) / d, (p2[1] - p1[1]) / d
    h = math.sqrt(max(0.0, r * r - (d / 2.0) ** 2)) * (1.0 if r > 0 else -1.0)
    cx = mid[0] + (-uy) * h
    cy = mid[1] + ux * h
    rad = math.hypot(p1[0] - cx, p1[1] - cy)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    n = max(4, int((abs(theta) * rad) / max(seg_len, 0.05)))
    pts = []
    for i in range(n + 1):
        a = a1 + theta * i / n
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


class TextEntity(Entity):
    kind = "TEXT"

    def __init__(self, pos, height, text, rotation=0.0, **kw):
        super().__init__(**kw)
        self.pos = tuple(pos)
        self.height = height
        self.text = text
        self.rotation = rotation

    def bbox(self):
        w = self.height * 0.6 * len(self.text)
        x, y = self.pos
        return (x, y, x + w, y + self.height)

    def translate(self, dx, dy):
        self.pos = (self.pos[0] + dx, self.pos[1] + dy)

    def rotate(self, cx, cy, ang):
        self.pos = _rot_pt(*self.pos, cx, cy, ang)
        self.rotation += ang

    def scale(self, cx, cy, f):
        self.pos = (cx + (self.pos[0] - cx) * f, cy + (self.pos[1] - cy) * f)
        self.height *= abs(f)

    def mirror(self, p1, p2):
        self.pos = _mirror_pt(*self.pos, p1, p2)

    def clone(self):
        return TextEntity(self.pos, self.height, self.text, self.rotation,
                           layer=self.layer, color=self.color)

    def to_polyline_points(self, seg_len=1.0):
        return [self.pos]


class Point(Entity):
    kind = "POINT"

    def __init__(self, pos, size=2.5, **kw):
        super().__init__(**kw)
        self.pos = tuple(pos)
        self.size = size

    def bbox(self):
        x, y = self.pos
        s = self.size
        return (x - s, y - s, x + s, y + s)

    def translate(self, dx, dy):
        self.pos = (self.pos[0] + dx, self.pos[1] + dy)

    def rotate(self, cx, cy, ang):
        self.pos = _rot_pt(*self.pos, cx, cy, ang)

    def scale(self, cx, cy, f):
        self.pos = (cx + (self.pos[0] - cx) * f, cy + (self.pos[1] - cy) * f)

    def mirror(self, p1, p2):
        self.pos = _mirror_pt(*self.pos, p1, p2)

    def clone(self):
        return Point(self.pos, self.size, layer=self.layer, color=self.color)

    def to_polyline_points(self, seg_len=1.0):
        return [self.pos]


class Ellipse(Entity):
    kind = "ELLIPSE"

    def __init__(self, center, rx, ry, rotation=0.0, **kw):
        super().__init__(**kw)
        self.center = tuple(center)
        self.rx = rx
        self.ry = ry
        self.rotation = rotation

    def bbox(self):
        cx, cy = self.center
        r = max(self.rx, self.ry)
        return (cx - r, cy - r, cx + r, cy + r)

    def translate(self, dx, dy):
        self.center = (self.center[0] + dx, self.center[1] + dy)

    def rotate(self, cx, cy, ang):
        self.center = _rot_pt(*self.center, cx, cy, ang)
        self.rotation += ang

    def scale(self, cx, cy, f):
        self.center = (cx + (self.center[0] - cx) * f, cy + (self.center[1] - cy) * f)
        self.rx *= abs(f)
        self.ry *= abs(f)

    def mirror(self, p1, p2):
        self.center = _mirror_pt(*self.center, p1, p2)
        self.rotation = -self.rotation

    def clone(self):
        return Ellipse(self.center, self.rx, self.ry, self.rotation,
                       layer=self.layer, color=self.color)

    def to_polyline_points(self, seg_len=1.0):
        n = max(24, int(2 * math.pi * max(self.rx, self.ry) / max(seg_len, 0.05)))
        cx, cy = self.center
        pts = []
        for i in range(n + 1):
            a = 2 * math.pi * i / n
            x = self.rx * math.cos(a)
            y = self.ry * math.sin(a)
            rx, ry = _rot_pt(x, y, 0, 0, self.rotation)
            pts.append((cx + rx, cy + ry))
        return pts


class Hatch(Entity):
    kind = "HATCH"

    def __init__(self, boundary, pattern="SOLID", **kw):
        super().__init__(**kw)
        self.boundary = [tuple(p) for p in boundary]
        self.pattern = pattern

    def bbox(self):
        xs = [p[0] for p in self.boundary]
        ys = [p[1] for p in self.boundary]
        return (min(xs), min(ys), max(xs), max(ys))

    def translate(self, dx, dy):
        self.boundary = [(x + dx, y + dy) for x, y in self.boundary]

    def rotate(self, cx, cy, ang):
        self.boundary = [_rot_pt(x, y, cx, cy, ang) for x, y in self.boundary]

    def scale(self, cx, cy, f):
        self.boundary = [(cx + (x - cx) * f, cy + (y - cy) * f) for x, y in self.boundary]

    def mirror(self, p1, p2):
        self.boundary = [_mirror_pt(x, y, p1, p2) for x, y in self.boundary]

    def clone(self):
        return Hatch(list(self.boundary), self.pattern, layer=self.layer, color=self.color)

    def to_polyline_points(self, seg_len=1.0):
        return list(self.boundary)


class Solid(Entity):
    kind = "SOLID"

    def __init__(self, points, **kw):
        super().__init__(**kw)
        self.points = [tuple(p) for p in points]

    def bbox(self):
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def translate(self, dx, dy):
        self.points = [(x + dx, y + dy) for x, y in self.points]

    def rotate(self, cx, cy, ang):
        self.points = [_rot_pt(x, y, cx, cy, ang) for x, y in self.points]

    def scale(self, cx, cy, f):
        self.points = [(cx + (x - cx) * f, cy + (y - cy) * f) for x, y in self.points]

    def mirror(self, p1, p2):
        self.points = [_mirror_pt(x, y, p1, p2) for x, y in self.points]

    def clone(self):
        return Solid(list(self.points), layer=self.layer, color=self.color)

    def to_polyline_points(self, seg_len=1.0):
        return list(self.points)


class Annotation(Entity):
    """Base for composite annotation entities (dimensions, leaders).

    Stores a list of primitive sub-entities (Line / Arc / TextEntity) that
    are rendered as one object but excluded from G-code generation (gcode.py
    only machines LINE/ARC/CIRCLE/LWPOLYLINE)."""
    kind = "ANNOTATION"

    def __init__(self, parts, **kw):
        super().__init__(**kw)
        self.parts = list(parts)
        self.sources = []   # measured entity(ies) this annotation is tied to
        self.defn = {}      # description used to recompute parts from sources

    def bbox(self):
        xs1, ys1, xs2, ys2 = [], [], [], []
        for part in self.parts:
            b = part.bbox()
            xs1.append(b[0]); ys1.append(b[1]); xs2.append(b[2]); ys2.append(b[3])
        if not xs1:
            return (0, 0, 0, 0)
        return (min(xs1), min(ys1), max(xs2), max(ys2))

    def translate(self, dx, dy):
        for part in self.parts:
            part.translate(dx, dy)

    def rotate(self, cx, cy, ang):
        for part in self.parts:
            part.rotate(cx, cy, ang)

    def scale(self, cx, cy, f):
        for part in self.parts:
            part.scale(cx, cy, f)

    def mirror(self, p1, p2):
        for part in self.parts:
            part.mirror(p1, p2)

    def clone(self):
        import copy
        return self._rebuild(copy.deepcopy(self.parts))

    def _rebuild(self, parts):
        return self.__class__(parts, layer=self.layer, color=self.color)

    def to_polyline_points(self, seg_len=1.0):
        # first line segment is the dimension/leader line, used for hit testing
        for part in self.parts:
            if part.kind == "LINE":
                return [part.p1, part.p2]
        if self.parts:
            return self.parts[0].to_polyline_points(seg_len)
        return []


class Dimension(Annotation):
    kind = "DIMENSION"

    def __init__(self, subtype, measurement, parts, **kw):
        super().__init__(parts, **kw)
        self.subtype = subtype
        self.measurement = measurement

    def _rebuild(self, parts):
        return Dimension(self.subtype, self.measurement, parts,
                         layer=self.layer, color=self.color)

    def apply_value(self, value):
        """Drive the source geometry so this dimension reads `value`
        (parametric / driven dimension, SolidWorks-style)."""
        t = self.subtype
        if t == "linear" and self.sources:
            e = self.sources[0]
            if e.kind == "LINE":
                p1, p2 = e.p1, e.p2
                d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                if d < 1e-9:
                    return
                ux, uy = (p2[0] - p1[0]) / d, (p2[1] - p1[1]) / d
                e.p2 = (p1[0] + ux * value, p1[1] + uy * value)
            elif e.kind == "LWPOLYLINE" and e.verts:
                pts = [(v[0], v[1]) for v in e.verts]
                p1, p2 = pts[0], pts[-1]
                d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                if d < 1e-9:
                    return
                f = value / d
                e.verts = [(p1[0] + (x - p1[0]) * f, p1[1] + (y - p1[1]) * f, v[2])
                           for (x, y, v) in e.verts]
        elif t in ("radial", "radius", "diameter") and self.sources:
            e = self.sources[0]
            r = value if not self.defn.get("diameter") else value / 2.0
            e.radius = r
        elif t == "angular" and len(self.sources) >= 2:
            l1, l2 = self.sources[0], self.sources[1]
            V = _line_intersection_full(l1, l2)
            if V is None:
                return
            loc = self.defn.get("loc") or (0.0, 0.0)
            # rotate l2 *within the same sector the user clicked* (reflex-safe):
            # measure the current clicked-sector span, then add (value - span)
            # so the line stays on the same side instead of flipping over.
            _, s, e, _, _ = _angular_sector(l1, l2, loc)
            cur_span = e - s  # CCW span of the clicked sector (may be > pi)
            rot = math.radians(value) - cur_span
            l2.p1 = _rot_pt(l2.p1[0], l2.p1[1], V[0], V[1], rot)
            l2.p2 = _rot_pt(l2.p2[0], l2.p2[1], V[0], V[1], rot)
            # remember the new sector by moving the loc marker to its midpoint,
            # so re-draws keep showing the driven value (even if reflex) and the
            # dim stays on the same side instead of snapping to the complement
            mid = (s + math.radians(value)) / 2.0
            dist = max(math.hypot(loc[0] - V[0], loc[1] - V[1]), 10.0)
            self.defn["loc"] = (V[0] + dist * math.cos(mid), V[1] + dist * math.sin(mid))
        # The typed value is authoritative for the displayed dimension text,
        # so the label always matches what the user entered (driven value),
        # even if the underlying geometry re-measures a complement/reflex.
        self.measurement = value
        self._driven = True
        self.recompute()


class Leader(Annotation):
    kind = "LEADER"

    def __init__(self, points, text, parts, **kw):
        super().__init__(parts, **kw)
        self.points = list(points)
        self.text = text

    def _rebuild(self, parts):
        return Leader(self.points, self.text, parts,
                      layer=self.layer, color=self.color)


# ---------------------------------------------------------------- dimension builders

def _arrow_ticks(p_tip, ux, uy, layer, ah=2.5):
    """Two short segments forming an arrowhead at p_tip pointing along (ux,uy)."""
    nx, ny = -uy, ux
    back = (p_tip[0] - ux * ah, p_tip[1] - uy * ah)
    left = (back[0] + nx * ah * 0.45, back[1] + ny * ah * 0.45)
    right = (back[0] - nx * ah * 0.45, back[1] - ny * ah * 0.45)
    return [Line(p_tip, left, layer=layer), Line(p_tip, right, layer=layer)]


def _make_linear_parts(p1, p2, loc, layer):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return []
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    off = (loc[0] - p1[0]) * nx + (loc[1] - p1[1]) * ny
    if abs(off) < 1e-6:
        off = 10.0
    ah = max(abs(off) * 0.09, L * 0.09, 1e-3)
    a1 = (p1[0] + nx * off, p1[1] + ny * off)
    a2 = (p2[0] + nx * off, p2[1] + ny * off)
    parts = [
        Line(p1, a1, layer=layer),
        Line(p2, a2, layer=layer),
        Line(a1, a2, layer=layer),
    ]
    parts += _arrow_ticks(a2, ux, uy, layer, ah)
    parts += _arrow_ticks(a1, -ux, -uy, layer, ah)
    mid = ((a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2)
    th = max(abs(off) * 0.11, L * 0.11, 1e-3)
    tpos = (mid[0] + nx * th * 0.7, mid[1] + ny * th * 0.7)
    parts.append(TextEntity(tpos, th, f"{L:.2f}", layer=layer))
    return parts


def build_linear_dim(p1, p2, loc, layer, sources=()):
    dim = Dimension("linear", math.hypot(p2[0] - p1[0], p2[1] - p1[1]),
                    _make_linear_parts(p1, p2, loc, layer), layer=layer)
    dim.sources = list(sources)
    dim.defn = {"type": "linear", "p1": p1, "p2": p2, "loc": loc}
    return dim


def _make_radius_parts(center, pt, layer, diameter):
    r = math.hypot(pt[0] - center[0], pt[1] - center[1])
    if r < 1e-9:
        return []
    ux, uy = (pt[0] - center[0]) / r, (pt[1] - center[1]) / r
    nx, ny = -uy, ux
    ah = max(r * 0.08, 1e-3)
    th = max(r * 0.12, 1e-3)
    if diameter:
        a = (center[0] - ux * r, center[1] - uy * r)
        b = (center[0] + ux * r, center[1] + uy * r)
        parts = [Line(a, b, layer=layer)]
        parts += _arrow_ticks(b, ux, uy, layer, ah)
        parts += _arrow_ticks(a, -ux, -uy, layer, ah)
        tpos = (center[0] + nx * th * 0.7, center[1] + ny * th * 0.7)
        text = f"{2 * r:.2f}"
    else:
        parts = [Line(center, pt, layer=layer)]
        parts += _arrow_ticks(center, ux, uy, layer, ah)
        tpos = (pt[0] + ux * ah * 1.4, pt[1] + uy * ah * 1.4)
        text = f"R{r:.2f}"
    parts.append(TextEntity(tpos, th, text, layer=layer))
    return parts


def build_radius_dim(center, pt, layer, diameter=False, sources=()):
    r = math.hypot(pt[0] - center[0], pt[1] - center[1]) or 1e-9
    ang = math.atan2(pt[1] - center[1], pt[0] - center[0])
    dim = Dimension("diameter" if diameter else "radius", r,
                    _make_radius_parts(center, pt, layer, diameter), layer=layer)
    dim.sources = list(sources)
    dim.defn = {"type": "radial", "center": center, "r": r, "ang": ang, "diameter": diameter}
    return dim


def _line_intersection_full(l1, l2):
    """Intersection of the (infinite) lines through l1 and l2 (None if parallel).
    AutoCAD extends the selected lines to find the angular-dimension vertex."""
    x1, y1 = l1.p1; x2, y2 = l1.p2
    x3, y3 = l2.p1; x4, y4 = l2.p2
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-9:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / d
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / d
    return (px, py)


def _unit(v):
    l = math.hypot(v[0], v[1])
    return (v[0] / l, v[1] / l) if l > 1e-9 else (1.0, 0.0)


def _angular_sector(l1, l2, loc):
    """Return (vertex, start_ang, end_ang, deg, radius) for an angular dim
    between two lines, AutoCAD-style: vertex at the (extended) line crossing,
    the drawn sector is the one containing `loc`, deg is the small angle."""
    V = _line_intersection_full(l1, l2)
    if V is None:
        # parallel lines: measure angle between their directions, pseudo vertex
        d1 = _unit((l1.p2[0] - l1.p1[0], l1.p2[1] - l1.p1[1]))
        d2 = _unit((l2.p2[0] - l2.p1[0], l2.p2[1] - l2.p1[1]))
        ang = abs(math.degrees(math.atan2(d2[1], d2[0]) - math.atan2(d1[1], d1[0])))
        ang = ang if ang <= 180 else 360 - ang
        m1 = ((l1.p1[0] + l1.p2[0]) / 2.0, (l1.p1[1] + l1.p2[1]) / 2.0)
        m2 = ((l2.p1[0] + l2.p2[0]) / 2.0, (l2.p1[1] + l2.p2[1]) / 2.0)
        V = ((m1[0] + m2[0]) / 2.0, (m1[1] + m2[1]) / 2.0)
        R = max(math.hypot(loc[0] - V[0], loc[1] - V[1]), 5.0)
        s = 0.0
        e = math.radians(ang) if ang > 0 else math.pi
        return V, s, e, ang, R
    # Treat each line as a RAY emanating from the vertex V (direction from V
    # toward the line's far end). Two rays -> two sectors, so a corner can be
    # dimensioned as reflex (> 180, the "outside" of the corner), which is
    # impossible with infinite bi-directional lines. This also fixes the
    # "dimension appears on the wrong/180 side" problem.
    rays = []
    for ln in (l1, l2):
        # choose the endpoint farther from the vertex as the outward direction
        d1 = (ln.p1[0] - V[0], ln.p1[1] - V[1])
        d2 = (ln.p2[0] - V[0], ln.p2[1] - V[1])
        if math.hypot(*d2) >= math.hypot(*d1):
            outward = d2
        else:
            outward = d1
        rays.append(math.atan2(outward[1], outward[0]))
    # two distinct rays -> two sectors [r0, r1) and [r1, r0+2pi)
    r0, r1 = sorted(rays)
    sectors = [(r0, r1), (r1, r0 + 2 * math.pi)]
    ang_loc = math.atan2(loc[1] - V[1], loc[0] - V[0]) % (2 * math.pi)
    s = e = None
    for a, b in sectors:
        if a <= ang_loc < b:
            s, e = a, b
            break
    if s is None:  # numerical fallback
        s, e = sectors[0]
    span = e - s
    deg = math.degrees(span)
    R = max(math.hypot(loc[0] - V[0], loc[1] - V[1]), 1e-3)
    return V, s, e, deg, R


def _make_angular_parts(v, start_ang, end_ang, r, layer, deg):
    r = max(r, 1e-3)
    ah = max(r * 0.08, 1e-3)
    th = max(r * 0.12, 1e-3)
    ea = end_ang if end_ang > start_ang else end_ang + 2 * math.pi
    a = (v[0] + r * math.cos(start_ang), v[1] + r * math.sin(start_ang))
    b = (v[0] + r * math.cos(ea), v[1] + r * math.sin(ea))
    ext1 = Line(v, a, layer=layer)          # extension line along first line
    ext2 = Line(v, b, layer=layer)          # extension line along second line
    arc = Arc(v, r, start_ang, ea, layer=layer)
    # arrowheads at the arc ends, pointing along the arc tangent
    ta_x, ta_y = -math.sin(start_ang), math.cos(start_ang)
    tb_x, tb_y = math.sin(ea), -math.cos(ea)
    arrows = _arrow_ticks(a, ta_x, ta_y, layer, ah) + _arrow_ticks(b, tb_x, tb_y, layer, ah)
    amid = (start_ang + ea) / 2.0
    tpos = (v[0] + (r + th * 0.6) * math.cos(amid), v[1] + (r + th * 0.6) * math.sin(amid))
    return [ext1, ext2, arc] + arrows + [TextEntity(tpos, th, f"{deg:.1f} deg", layer=layer)]


def build_angular_dim(l1, l2, loc, layer, sources=()):
    V, s, e, deg, R = _angular_sector(l1, l2, loc)
    dim = Dimension("angular", deg, _make_angular_parts(V, s, e, R, layer, deg), layer=layer)
    dim.sources = list(sources)
    dim.defn = {"type": "angular", "loc": loc}
    return dim


def _make_leader_parts(points, text, layer):
    parts = []
    if len(points) >= 2:
        for i in range(len(points) - 1):
            parts.append(Line(points[i], points[i + 1], layer=layer))
        d = (points[1][0] - points[0][0], points[1][1] - points[0][1])
        L = math.hypot(*d) or 1.0
        ux, uy = d[0] / L, d[1] / L
        parts += _arrow_ticks(points[0], ux, uy, layer)
    if text:
        last = points[-1]
        parts.append(TextEntity((last[0] + 4.0, last[1]), 3.0, text, layer=layer))
    return parts


def build_leader(points, text, layer):
    return Leader(points, text, _make_leader_parts(points, text, layer), layer=layer)


def _line_intersection(l1, l2):
    x1, y1 = l1.p1; x2, y2 = l1.p2
    x3, y3 = l2.p1; x4, y4 = l2.p2
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-9:
        return None
    px = ((x1*y2 - y1*x2)*(x3-x4) - (x1-x2)*(x3*y4 - y3*x4)) / d
    py = ((x1*y2 - y1*x2)*(y3-y4) - (y1-y2)*(x3*y4 - y3*x4)) / d
    if (min(x1, x2) - 1e-9 <= px <= max(x1, x2) + 1e-9 and
            min(x3, x4) - 1e-9 <= px <= max(x3, x4) + 1e-9 and
            min(y1, y2) - 1e-9 <= py <= max(y1, y2) + 1e-9 and
            min(y3, y4) - 1e-9 <= py <= max(y3, y4) + 1e-9):
        return (px, py)
    return None


def _far_end(line, ip):
    d1 = math.hypot(line.p1[0] - ip[0], line.p1[1] - ip[1])
    d2 = math.hypot(line.p2[0] - ip[0], line.p2[1] - ip[1])
    return line.p2 if d1 < d2 else line.p1


def _recompute_annotation(ann):
    """Re-derive an associative annotation's parts from its source entities'
    CURRENT geometry. Called on every redraw so dimensions follow their
    source entities (AutoCAD-style associativity)."""
    d = ann.defn
    if not d:
        return
    t = d.get("type")
    if t == "linear":
        p1, p2, loc = d["p1"], d["p2"], d["loc"]
        if ann.sources:
            e = ann.sources[0]
            if e.kind == "LINE":
                p1, p2 = e.p1, e.p2
            elif e.kind == "LWPOLYLINE" and e.verts:
                p1 = (e.verts[0][0], e.verts[0][1])
                p2 = (e.verts[-1][0], e.verts[-1][1])
        ann.parts = _make_linear_parts(p1, p2, loc, ann.layer)
        ann.measurement = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    elif t == "radial":
        center, r, ang, dia = d["center"], d["r"], d["ang"], d["diameter"]
        if ann.sources:
            src = ann.sources[0]
            center = src.center
            r = src.radius
        pt = (center[0] + r * math.cos(ang), center[1] + r * math.sin(ang))
        ann.parts = _make_radius_parts(center, pt, ann.layer, dia)
        ann.measurement = r
    elif t == "angular":
        if len(ann.sources) >= 2:
            l1, l2 = ann.sources[0], ann.sources[1]
            loc = d.get("loc") or (0.0, 0.0)
            # associative: re-measure the sector the user clicked (reflex-capable)
            V, s, e, deg, R = _angular_sector(l1, l2, loc)
            ann.parts = _make_angular_parts(V, s, e, R, ann.layer, deg)
            # Keep the user-driven value as the displayed text. Only re-measure
            # when the user has NOT explicitly set a value, otherwise the label
            # can flip to the complement (e.g. 50 -> 270). The arc still follows
            # the actual geometry via ann.parts above.
            if not getattr(ann, "_driven", False):
                ann.measurement = deg


Annotation.recompute = _recompute_annotation


class Drawing:
    """Holds the full entity set + layers, plus undo/redo stacks."""

    def __init__(self):
        self.entities = []
        self.layers = {"0": {"color": 7, "on": True, "frozen": False}}
        self.current_layer = "0"
        self.filepath = None
        self._undo = []
        self._redo = []
        # ---- parametric / constraints model ----
        self.constraints = []     # list of Constraint objects
        self.variables = {}       # name -> Variable
        self._cid = 0

    def add(self, ent):
        self.entities.append(ent)
        return ent

    def remove(self, ent):
        if ent in self.entities:
            self.entities.remove(ent)

    def selected(self):
        return [e for e in self.entities if e.selected]

    def clear_selection(self):
        for e in self.entities:
            e.selected = False

    def snapshot(self):
        import copy
        return {
            "entities": copy.deepcopy(self.entities),
            "layers": copy.deepcopy(self.layers),
            "current_layer": self.current_layer,
            "constraints": copy.deepcopy(self.constraints),
            "variables": copy.deepcopy(self.variables),
            "_cid": self._cid,
        }

    def _restore(self, snap):
        import copy
        self.entities = copy.deepcopy(snap["entities"])
        self.layers = copy.deepcopy(snap["layers"])
        self.current_layer = snap["current_layer"]
        self.constraints = copy.deepcopy(snap["constraints"])
        self.variables = copy.deepcopy(snap["variables"])
        self._cid = snap["_cid"]

    def push_undo(self):
        self._undo.append(self.snapshot())
        if len(self._undo) > 200:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(self.snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(self.snapshot())
        self._restore(self._redo.pop())
        return True

    def bbox(self):
        if not self.entities:
            return (0, 0, 100, 100)
        xs1, ys1, xs2, ys2 = [], [], [], []
        for e in self.entities:
            b = e.bbox()
            xs1.append(b[0]); ys1.append(b[1]); xs2.append(b[2]); ys2.append(b[3])
        return (min(xs1), min(ys1), max(xs2), max(ys2))

    # ---- parametric / constraints API ----
    def add_constraint(self, con):
        self._cid += 1
        con._id = self._cid
        self.constraints.append(con)
        return con

    def remove_constraint(self, con):
        if con in self.constraints:
            self.constraints.remove(con)

    def clear_constraints(self):
        self.constraints = []

    def add_variable(self, name, value, desc=""):
        from constraints import Variable
        self.variables[name] = Variable(name, value, desc)
        return self.variables[name]

    def set_variable(self, name, value):
        if name in self.variables:
            self.variables[name].value = float(value)

    def solve_constraints(self, iterations=200, tol=1e-6):
        """Run the parametric solver so geometry matches its constraints.
        Returns the final max residual (0 == fully solved)."""
        if not self.constraints:
            return 0.0
        from constraints import Solver
        solver = Solver(self.constraints, self.variables)
        return solver.solve(iterations=iterations, tol=tol)

    def autoconstrain_selection(self, tol=1e-3):
        """Infer geometric constraints for the given/full selection, SolidWorks
        style, and add them to the drawing.  Returns the number added."""
        sel = self.selected() or self.entities
        from constraints import autoconstrain
        cons = autoconstrain(sel, tol=tol)
        before = len(self.constraints)
        for c in cons:
            self.add_constraint(c)
        return len(self.constraints) - before
