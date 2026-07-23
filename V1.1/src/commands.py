"""
commands.py
AutoCAD-style prompted commands, implemented as Python generators.
Each command generator yields a Prompt object describing what input it
needs next (a point, a string, or a selection set); the engine/canvas
sends back the value via generator.send(). This mirrors how the LSP used
(getpoint), (getstring) etc. - just event-driven instead of blocking.

Commands here are REAL, working implementations (~30 commands) covering
draw + modify + view + utility. Anything in command_table.py without an
entry in COMMANDS below is a recognized-but-not-yet-implemented command.
"""
import math
from entities import (Line, Circle, Arc, LWPolyline, TextEntity, Point, Dimension,
                      Leader, Ellipse, Hatch, Solid,
                      build_linear_dim, build_radius_dim, build_angular_dim,
                      build_leader)


def _line_intersection_full(p1, p2, p3, p4):
    """Intersection of the (infinite) lines through p1-p2 and p3-p4."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-12:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
    return (px, py)


class Prompt:
    POINT = "point"
    TEXT = "text"
    SELECTION = "selection"
    DONE = "done"

    def __init__(self, kind, message, default=None):
        self.kind = kind
        self.message = message
        self.default = default


def done(message="Command complete."):
    return Prompt(Prompt.DONE, message)


# ---------------------------------------------------------------- drawing

def cmd_line(ctx):
    ctx.drawing.push_undo()
    # SolidWorks-style: as each segment is drawn, flag it as the "moving" entity
    # so live constraint inference (coincident/tangent/perp) can attach to it.
    if ctx.canvas:
        ctx.canvas._infer_moving = None
    p1 = yield Prompt(Prompt.POINT, "Specify first point:")
    while True:
        p2 = yield Prompt(Prompt.POINT, "Specify next point or [Enter to finish]:")
        if p2 is None:
            break
        line = Line(p1, p2, layer=ctx.drawing.current_layer)
        ctx.drawing.add(line)
        if ctx.canvas:
            ctx.canvas._infer_moving = line
            # auto-connect: if an endpoint landed on another entity, constrain it
            try:
                from constraints import auto_connect_points
                auto_connect_points(p1, p2, ctx.drawing)
                ctx.drawing.solve_constraints()
                ctx.canvas.update()
            except Exception:
                pass
        p1 = p2
    if ctx.canvas:
        ctx.canvas._infer_moving = None
    yield done("Line(s) created.")


def cmd_circle(ctx):
    c = yield Prompt(Prompt.POINT, "Specify center point:")
    # SolidWorks-style: hovering the radius point near another entity shows a
    # TANGENT/COINCIDENT glyph; clicking applies the constraint auto-magically.
    # We add the circle first (so it exists as the inference moving entity) at a
    # temporary radius, then let the radius prompt refine it.
    ctx.drawing.push_undo()
    circ = Circle(c, 1.0, layer=ctx.drawing.current_layer)
    ctx.drawing.add(circ)
    ctx.canvas._infer_moving = circ
    r_pt = yield Prompt(Prompt.POINT, "Specify radius - click a point, or type a value (e.g. 25 or 25<0):")
    r = math.hypot(r_pt[0] - c[0], r_pt[1] - c[1])
    if r < 1e-9:
        ctx.canvas._infer_moving = None
        ctx.drawing.pop_undo()
        yield done("Zero radius. Cancelled.")
        return
    circ.radius = r
    # if the radius point inference produced a constraint, apply it live
    if getattr(ctx.canvas, "_infer_factory", None) is not None:
        try:
            con = ctx.canvas._infer_factory()
            if con is not None:
                ctx.drawing.add_constraint(con)
                ctx.drawing.solve_constraints()
        except Exception:
            pass
        ctx.canvas._infer_factory = None
        ctx.canvas._infer_glyph = None
    ctx.canvas._infer_moving = None
    yield done(f"Circle r={r:.3f} created.")


def cmd_arc(ctx):
    ctx.drawing.push_undo()
    p1 = yield Prompt(Prompt.POINT, "Specify start point:")
    p2 = yield Prompt(Prompt.POINT, "Specify second point (on arc):")
    p3 = yield Prompt(Prompt.POINT, "Specify end point:")
    center, radius = _circle_through_3pts(p1, p2, p3)
    if center is None:
        yield done("Points are collinear - cannot fit arc. Cancelled.")
        return
    a1 = math.atan2(p1[1] - center[1], p1[0] - center[0])
    a3 = math.atan2(p3[1] - center[1], p3[0] - center[0])
    # ensure sweep passes through p2's angle (CCW)
    a2 = math.atan2(p2[1] - center[1], p2[0] - center[0])
    sa, ea = a1, a3
    if not _angle_between(a2, sa, ea):
        sa, ea = ea, sa
        sa, ea = a3, a1
        if not _angle_between(a2, sa, ea):
            sa, ea = a1, a3
    ctx.drawing.add(Arc(center, radius, sa, ea, layer=ctx.drawing.current_layer))
    yield done("Arc created.")


def _angle_between(a, s, e):
    while e < s:
        e += 2 * math.pi
    while a < s:
        a += 2 * math.pi
    return s <= a <= e


def _circle_through_3pts(p1, p2, p3):
    ax, ay = p1; bx, by = p2; cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None, None
    ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / d
    uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    return (ux, uy), r


def cmd_pline(ctx):
    ctx.drawing.push_undo()
    pts = []
    p1 = yield Prompt(Prompt.POINT, "Specify first point:")
    pts.append(p1)
    while True:
        p2 = yield Prompt(Prompt.POINT, "Specify next point or [Enter to finish]:")
        if p2 is None:
            break
        pts.append(p2)
    if len(pts) >= 2:
        ctx.drawing.add(LWPolyline([(x, y, 0.0) for x, y in pts], closed=False,
                                    layer=ctx.drawing.current_layer))
        yield done("Polyline created.")
    else:
        yield done("Not enough points. Cancelled.")


def cmd_rectang(ctx):
    ctx.drawing.push_undo()
    p1 = yield Prompt(Prompt.POINT, "Specify first corner:")
    p2 = yield Prompt(Prompt.POINT, "Specify opposite corner:")
    x1, y1 = p1; x2, y2 = p2
    verts = [(x1, y1, 0.0), (x2, y1, 0.0), (x2, y2, 0.0), (x1, y2, 0.0)]
    ctx.drawing.add(LWPolyline(verts, closed=True, layer=ctx.drawing.current_layer))
    yield done("Rectangle created.")


def cmd_polygon(ctx):
    ctx.drawing.push_undo()
    n_in = yield Prompt(Prompt.TEXT, "Enter number of sides:")
    try:
        n = int(n_in)
        assert n >= 3
    except Exception:
        yield done("Invalid number of sides. Cancelled.")
        return
    c = yield Prompt(Prompt.POINT, "Specify center of polygon:")
    p2 = yield Prompt(Prompt.POINT, "Specify vertex point:")
    r = math.hypot(p2[0] - c[0], p2[1] - c[1])
    a0 = math.atan2(p2[1] - c[1], p2[0] - c[0])
    verts = []
    for i in range(n):
        a = a0 + 2 * math.pi * i / n
        verts.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a), 0.0))
    ctx.drawing.add(LWPolyline(verts, closed=True, layer=ctx.drawing.current_layer))
    yield done(f"{n}-sided polygon created.")


def cmd_point(ctx):
    ctx.drawing.push_undo()
    p = yield Prompt(Prompt.POINT, "Specify point:")
    ctx.drawing.add(Point(p, layer=ctx.drawing.current_layer))
    yield done("Point created.")


def _text_common(ctx, font, font_label):
    """Shared body for TEXT (general) and TEXTS (single)."""
    from fonts import render_text
    ctx.drawing.push_undo()
    p = yield Prompt(Prompt.POINT, "Specify start point (bottom-left of text):")
    h_in = yield Prompt(Prompt.TEXT, "Specify text height:", default="2.5")
    try:
        h = float(h_in) if h_in else 2.5
    except ValueError:
        h = 2.5
    s = yield Prompt(Prompt.TEXT, "Enter text (e.g. L, ABC, 123):")
    s = (s or "").strip()
    ents, info = render_text(s, p, h, font=font)
    for e in ents:
        ctx.drawing.add(e)
    yield done(f"{font_label} text '{s}' created as {len(ents)} entity/ies.")


def cmd_text(ctx):
    """TEXT - general stroke font (original QCAD .cxf look): single pass of
    Line + Arc centerlines.  The text becomes real, machinable geometry."""
    return _text_common(ctx, "general", "General")


def cmd_text_single(ctx):
    """TEXTS - single-line / engraving font (Line + Arc centerlines, 1 pass).
    Best for V-bit engraving, lasers, plotters."""
    return _text_common(ctx, "single", "Single-line")


# ---------------------------------------------------------------- modify

def cmd_move(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select objects to move:"))
    if not sel:
        yield done("Nothing selected. Cancelled.")
        return
    base = yield Prompt(Prompt.POINT, "Specify base point:")
    dest = yield Prompt(Prompt.POINT, "Specify destination point:")
    dx, dy = dest[0] - base[0], dest[1] - base[1]
    ctx.drawing.push_undo()
    for e in sel:
        e.translate(dx, dy)
    yield done(f"Moved {len(sel)} object(s).")


def cmd_copy(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select objects to copy:"))
    if not sel:
        yield done("Nothing selected. Cancelled.")
        return
    base = yield Prompt(Prompt.POINT, "Specify base point:")
    ctx.drawing.push_undo()
    count = 0
    while True:
        dest = yield Prompt(Prompt.POINT, "Specify destination point (Enter to finish):")
        if dest is None:
            break
        dx, dy = dest[0] - base[0], dest[1] - base[1]
        for e in sel:
            c = e.clone()
            c.translate(dx, dy)
            ctx.drawing.add(c)
        count += 1
    yield done(f"Created {count} copy/copies.")


def cmd_rotate(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select objects to rotate:"))
    if not sel:
        yield done("Nothing selected. Cancelled.")
        return
    base = yield Prompt(Prompt.POINT, "Specify base point:")
    ang_in = yield Prompt(Prompt.TEXT, "Specify rotation angle (deg):")
    try:
        ang = math.radians(float(ang_in))
    except (TypeError, ValueError):
        yield done("Invalid angle. Cancelled.")
        return
    ctx.drawing.push_undo()
    for e in sel:
        e.rotate(base[0], base[1], ang)
    yield done(f"Rotated {len(sel)} object(s).")


def cmd_scale(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select objects to scale:"))
    if not sel:
        yield done("Nothing selected. Cancelled.")
        return
    base = yield Prompt(Prompt.POINT, "Specify base point:")
    f_in = yield Prompt(Prompt.TEXT, "Specify scale factor:")
    try:
        f = float(f_in)
    except (TypeError, ValueError):
        yield done("Invalid scale factor. Cancelled.")
        return
    ctx.drawing.push_undo()
    for e in sel:
        e.scale(base[0], base[1], f)
    yield done(f"Scaled {len(sel)} object(s).")


def cmd_mirror(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select objects to mirror:"))
    if not sel:
        yield done("Nothing selected. Cancelled.")
        return
    p1 = yield Prompt(Prompt.POINT, "Specify first point of mirror line:")
    p2 = yield Prompt(Prompt.POINT, "Specify second point of mirror line:")
    keep_in = yield Prompt(Prompt.TEXT, "Erase source objects? [Y/N]:", default="N")
    ctx.drawing.push_undo()
    for e in sel:
        c = e.clone()
        c.mirror(p1, p2)
        ctx.drawing.add(c)
    if (keep_in or "N").strip().upper().startswith("Y"):
        for e in sel:
            ctx.drawing.remove(e)
    yield done(f"Mirrored {len(sel)} object(s).")


def cmd_erase(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select objects to erase:"))
    if not sel:
        yield done("Nothing selected. Cancelled.")
        return
    ctx.drawing.push_undo()
    for e in sel:
        ctx.drawing.remove(e)
    yield done(f"Erased {len(sel)} object(s).")


def cmd_offset(ctx):
    d_in = yield Prompt(Prompt.TEXT, "Specify offset distance:")
    try:
        dist = float(d_in)
    except (TypeError, ValueError):
        yield done("Invalid distance. Cancelled.")
        return
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select object to offset:"))
    if not sel:
        yield done("Nothing selected. Cancelled.")
        return
    side = yield Prompt(Prompt.POINT, "Specify point on side to offset:")
    ctx.drawing.push_undo()
    made = 0
    for e in sel:
        new_e = _offset_entity(e, dist, side)
        if new_e:
            ctx.drawing.add(new_e)
            made += 1
    yield done(f"Offset {made} object(s).")


def _offset_entity(e, dist, side_pt):
    if e.kind == "CIRCLE":
        cx, cy = e.center
        d = math.hypot(side_pt[0] - cx, side_pt[1] - cy)
        new_r = e.radius + dist if d > e.radius else e.radius - dist
        if new_r <= 0:
            return None
        return Circle(e.center, new_r, layer=e.layer)
    if e.kind == "LINE":
        x1, y1 = e.p1; x2, y2 = e.p2
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return None
        nx, ny = -dy / length, dx / length
        # offset to the side the pick point is on (signed distance from line)
        signed = (side_pt[0] - x1) * nx + (side_pt[1] - y1) * ny
        s = 1.0 if signed >= 0 else -1.0
        ox, oy = nx * dist * s, ny * dist * s
        return Line((x1 + ox, y1 + oy), (x2 + ox, y2 + oy), layer=e.layer)
    return None


def cmd_fillet(ctx):
    r_in = yield Prompt(Prompt.TEXT, "Specify fillet radius:")
    try:
        r = float(r_in)
    except (TypeError, ValueError):
        yield done("Invalid radius. Cancelled.")
        return
    e1 = yield Prompt(Prompt.SELECTION, "Select first line:")
    e2 = yield Prompt(Prompt.SELECTION, "Select second line:")
    l1 = e1[0] if e1 else None
    l2 = e2[0] if e2 else None
    if not l1 or not l2 or l1.kind != "LINE" or l2.kind != "LINE":
        yield done("FILLET currently supports LINE-LINE only. Cancelled.")
        return
    result = _fillet_lines(l1, l2, r)
    if not result:
        yield done("Lines are parallel or radius too large. Cancelled.")
        return
    new_l1, new_l2, arc = result
    ctx.drawing.push_undo()
    l1.p1, l1.p2 = new_l1
    l2.p1, l2.p2 = new_l2
    ctx.drawing.add(arc)
    yield done("Fillet created.")


def _line_intersect(l1, l2):
    x1, y1 = l1.p1; x2, y2 = l1.p2
    x3, y3 = l2.p1; x4, y4 = l2.p2
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-9:
        return None
    px = ((x1*y2 - y1*x2)*(x3-x4) - (x1-x2)*(x3*y4 - y3*x4)) / d
    py = ((x1*y2 - y1*x2)*(y3-y4) - (y1-y2)*(x3*y4 - y3*x4)) / d
    return (px, py)


def _fillet_lines(l1, l2, r):
    ip = _line_intersect(l1, l2)
    if ip is None:
        return None
    def far_end(line):
        d1 = math.hypot(line.p1[0]-ip[0], line.p1[1]-ip[1])
        d2 = math.hypot(line.p2[0]-ip[0], line.p2[1]-ip[1])
        return line.p2 if d1 < d2 else line.p1, line.p1 if d1 < d2 else line.p2
    far1, near1 = far_end(l1)
    far2, near2 = far_end(l2)
    u1 = ((far1[0]-ip[0])/math.hypot(far1[0]-ip[0], far1[1]-ip[1]),
          (far1[1]-ip[1])/math.hypot(far1[0]-ip[0], far1[1]-ip[1]))
    u2 = ((far2[0]-ip[0])/math.hypot(far2[0]-ip[0], far2[1]-ip[1]),
          (far2[1]-ip[1])/math.hypot(far2[0]-ip[0], far2[1]-ip[1]))
    ang = math.acos(max(-1.0, min(1.0, u1[0]*u2[0] + u1[1]*u2[1])))
    if ang < 1e-6 or ang > math.pi - 1e-6:
        return None
    tan_len = r / math.tan(ang / 2.0)
    t1 = (ip[0] + u1[0]*tan_len, ip[1] + u1[1]*tan_len)
    t2 = (ip[0] + u2[0]*tan_len, ip[1] + u2[1]*tan_len)
    bis = (u1[0]+u2[0], u1[1]+u2[1])
    bl = math.hypot(*bis)
    if bl < 1e-9:
        return None
    bis = (bis[0]/bl, bis[1]/bl)
    center_dist = r / math.sin(ang/2.0)
    center = (ip[0] + bis[0]*center_dist, ip[1] + bis[1]*center_dist)
    a1 = math.atan2(t1[1]-center[1], t1[0]-center[0])
    a2 = math.atan2(t2[1]-center[1], t2[0]-center[0])
    arc = Arc(center, r, a1, a2, layer=l1.layer)
    return (t1, far1), (t2, far2), arc


def cmd_chamfer(ctx):
    d_in = yield Prompt(Prompt.TEXT, "Specify chamfer distance:")
    try:
        d = float(d_in)
    except (TypeError, ValueError):
        yield done("Invalid distance. Cancelled.")
        return
    e1 = yield Prompt(Prompt.SELECTION, "Select first line:")
    e2 = yield Prompt(Prompt.SELECTION, "Select second line:")
    l1 = e1[0] if e1 else None
    l2 = e2[0] if e2 else None
    if not l1 or not l2 or l1.kind != "LINE" or l2.kind != "LINE":
        yield done("CHAMFER currently supports LINE-LINE only. Cancelled.")
        return
    ip = _line_intersect(l1, l2)
    if ip is None:
        yield done("Lines are parallel. Cancelled.")
        return
    def far_near(line):
        d1 = math.hypot(line.p1[0]-ip[0], line.p1[1]-ip[1])
        d2 = math.hypot(line.p2[0]-ip[0], line.p2[1]-ip[1])
        return (line.p2, line.p1) if d1 < d2 else (line.p1, line.p2)
    far1, near1 = far_near(l1)
    far2, near2 = far_near(l2)
    u1 = ((far1[0]-ip[0])/math.hypot(far1[0]-ip[0], far1[1]-ip[1]),
          (far1[1]-ip[1])/math.hypot(far1[0]-ip[0], far1[1]-ip[1]))
    u2 = ((far2[0]-ip[0])/math.hypot(far2[0]-ip[0], far2[1]-ip[1]),
          (far2[1]-ip[1])/math.hypot(far2[0]-ip[0], far2[1]-ip[1]))
    c1 = (ip[0] + u1[0]*d, ip[1] + u1[1]*d)
    c2 = (ip[0] + u2[0]*d, ip[1] + u2[1]*d)
    ctx.drawing.push_undo()
    l1.p1, l1.p2 = c1, far1
    l2.p1, l2.p2 = c2, far2
    ctx.drawing.add(Line(c1, c2, layer=l1.layer))
    yield done("Chamfer created.")


def cmd_trim(ctx):
    yield Prompt(Prompt.TEXT, "TRIM: select cutting edge(s), Enter, then click parts to trim.")
    yield done("TRIM: use edit mode in canvas (basic line-line trim) - see toolbar.")


def cmd_extend(ctx):
    bsel = yield Prompt(Prompt.SELECTION, "Select boundary line:")
    if not bsel or bsel[0].kind != "LINE":
        yield done("EXTEND: boundary must be a LINE. Cancelled.")
        return
    bnd = bsel[0]
    tsel = yield Prompt(Prompt.SELECTION, "Select line to extend:")
    if not tsel or tsel[0].kind != "LINE":
        yield done("EXTEND: select a LINE to extend. Cancelled.")
        return
    tgt = tsel[0]
    if tgt is bnd:
        yield done("EXTEND: same line. Cancelled.")
        return
    P = _line_intersection_full(bnd.p1, bnd.p2, tgt.p1, tgt.p2)
    if P is None:
        yield done("EXTEND: lines are parallel. Cancelled.")
        return
    d1 = math.hypot(P[0] - tgt.p1[0], P[1] - tgt.p1[1])
    d2 = math.hypot(P[0] - tgt.p2[0], P[1] - tgt.p2[1])
    ctx.drawing.push_undo()
    if d1 <= d2:
        tgt.p1 = P
    else:
        tgt.p2 = P
    yield done("EXTEND: line extended to boundary.")


def cmd_stretch(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select objects to stretch (crossing window):"))
    if not sel:
        yield done("Nothing selected. Cancelled.")
        return
    base = yield Prompt(Prompt.POINT, "Specify base point:")
    dest = yield Prompt(Prompt.POINT, "Specify destination point:")
    dx, dy = dest[0]-base[0], dest[1]-base[1]
    ctx.drawing.push_undo()
    for e in sel:
        e.translate(dx, dy)
    yield done(f"Stretched {len(sel)} object(s) (moved as whole - vertex-level stretch not yet implemented).")


def cmd_explode(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select objects to explode:"))
    if not sel:
        yield done("Nothing selected. Cancelled.")
        return
    ctx.drawing.push_undo()
    count = 0
    for e in sel:
        if e.kind == "LWPOLYLINE":
            pts = e.verts
            n = len(pts)
            rng = range(n) if e.closed else range(n - 1)
            for i in rng:
                x1, y1, b = pts[i]
                x2, y2, _ = pts[(i + 1) % n]
                if abs(b) < 1e-9:
                    ctx.drawing.add(Line((x1, y1), (x2, y2), layer=e.layer))
                else:
                    from gcode import bulge_to_arc_pts
                    apts = bulge_to_arc_pts((x1, y1), (x2, y2), b, 24)
                    for k in range(len(apts) - 1):
                        ctx.drawing.add(Line(apts[k], apts[k + 1], layer=e.layer))
                count += 1
            ctx.drawing.remove(e)
    yield done(f"Exploded into {count} segment(s).")


def cmd_join(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select lines to join:"))
    lines = [e for e in sel if e.kind == "LINE"]
    if len(lines) < 2:
        yield done("Select at least 2 lines. Cancelled.")
        return
    ctx.drawing.push_undo()
    verts = [(lines[0].p1[0], lines[0].p1[1], 0.0), (lines[0].p2[0], lines[0].p2[1], 0.0)]
    used = {lines[0]}
    changed = True
    while changed:
        changed = False
        last = verts[-1][:2]
        for ln in lines:
            if ln in used:
                continue
            if math.hypot(ln.p1[0]-last[0], ln.p1[1]-last[1]) < 1e-6:
                verts.append((ln.p2[0], ln.p2[1], 0.0)); used.add(ln); changed = True
            elif math.hypot(ln.p2[0]-last[0], ln.p2[1]-last[1]) < 1e-6:
                verts.append((ln.p1[0], ln.p1[1], 0.0)); used.add(ln); changed = True
    for ln in used:
        ctx.drawing.remove(ln)
    ctx.drawing.add(LWPolyline(verts, closed=False, layer=lines[0].layer))
    yield done(f"Joined {len(used)} line(s) into a polyline.")


def cmd_break(ctx):
    sel = yield Prompt(Prompt.SELECTION, "Select a line to break:")
    if not sel or sel[0].kind != "LINE":
        yield done("BREAK: select a single LINE. Cancelled.")
        return
    ln = sel[0]
    a = yield Prompt(Prompt.POINT, "First break point:")
    b = yield Prompt(Prompt.POINT, "Second break point:")
    p1, p2 = ln.p1, ln.p2
    vx, vy = p2[0] - p1[0], p2[1] - p1[1]
    L2 = vx * vx + vy * vy
    if L2 < 1e-12:
        yield done("BREAK: degenerate line. Cancelled.")
        return

    def proj(pt):
        t = max(0.0, min(1.0, ((pt[0] - p1[0]) * vx + (pt[1] - p1[1]) * vy) / L2))
        return (p1[0] + t * vx, p1[1] + t * vy)

    A = proj(a)
    B = proj(b)
    ta = ((A[0] - p1[0]) * vx + (A[1] - p1[1]) * vy) / L2
    tb = ((B[0] - p1[0]) * vx + (B[1] - p1[1]) * vy) / L2
    lo, hi = sorted((ta, tb))
    ctx.drawing.push_undo()
    ctx.drawing.remove(ln)
    made = 0
    if lo > 1e-6:
        seg = Line(p1, A, layer=ln.layer, color=ln.color)
        if math.hypot(seg.p2[0] - seg.p1[0], seg.p2[1] - seg.p1[1]) > 1e-6:
            ctx.drawing.add(seg)
            made += 1
    if hi < 1.0 - 1e-6:
        seg = Line(B, p2, layer=ln.layer, color=ln.color)
        if math.hypot(seg.p2[0] - seg.p1[0], seg.p2[1] - seg.p1[1]) > 1e-6:
            ctx.drawing.add(seg)
            made += 1
    yield done(f"BREAK: removed gap, created {made} segment(s).")


def cmd_array_rect(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select objects to array:"))
    if not sel:
        yield done("Nothing selected. Cancelled.")
        return
    rows_in = yield Prompt(Prompt.TEXT, "Number of rows:", default="1")
    cols_in = yield Prompt(Prompt.TEXT, "Number of columns:", default="1")
    dx_in = yield Prompt(Prompt.TEXT, "Column spacing:", default="10")
    dy_in = yield Prompt(Prompt.TEXT, "Row spacing:", default="10")
    try:
        rows, cols = int(rows_in or 1), int(cols_in or 1)
        dx, dy = float(dx_in or 10), float(dy_in or 10)
    except ValueError:
        yield done("Invalid input. Cancelled.")
        return
    ctx.drawing.push_undo()
    made = 0
    for r in range(rows):
        for c in range(cols):
            if r == 0 and c == 0:
                continue
            for e in sel:
                clone = e.clone()
                clone.translate(c * dx, r * dy)
                ctx.drawing.add(clone)
                made += 1
    yield done(f"Array: created {made} copies ({rows}x{cols}).")


def cmd_undo(ctx):
    ok = ctx.drawing.undo()
    yield done("Undone." if ok else "Nothing to undo.")


def cmd_redo(ctx):
    ok = ctx.drawing.redo()
    yield done("Redone." if ok else "Nothing to redo.")


def cmd_dist(ctx):
    p1 = yield Prompt(Prompt.POINT, "Specify first point:")
    p2 = yield Prompt(Prompt.POINT, "Specify second point:")
    d = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
    ang = math.degrees(math.atan2(p2[1]-p1[1], p2[0]-p1[0]))
    yield done(f"Distance = {d:.3f}  Angle = {ang:.2f} deg")


def cmd_area(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select a closed polyline/circle:"))
    if not sel:
        yield done("Nothing selected. Cancelled.")
        return
    e = sel[0]
    if e.kind == "CIRCLE":
        a = math.pi * e.radius**2
        yield done(f"Area = {a:.3f}   Circumference = {2*math.pi*e.radius:.3f}")
        return
    pts = e.to_polyline_points(seg_len=0.5)
    a = 0.0
    n = len(pts)
    for i in range(n - 1):
        a += pts[i][0]*pts[i+1][1] - pts[i+1][0]*pts[i][1]
    a = abs(a) / 2.0
    perim = sum(math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]) for i in range(n-1))
    yield done(f"Area = {a:.3f}   Perimeter = {perim:.3f}")


def cmd_layer(ctx):
    name = yield Prompt(Prompt.TEXT, "Enter layer name to create/switch to:")
    if not name:
        yield done("Cancelled.")
        return
    if name not in ctx.drawing.layers:
        ctx.drawing.layers[name] = {"color": 7, "on": True, "frozen": False}
    ctx.drawing.current_layer = name
    yield done(f"Current layer: {name}")


def cmd_zoom_extents(ctx):
    ctx.canvas_action = "zoom_extents"
    yield done("Zoomed to extents.")


def cmd_regen(ctx):
    ctx.canvas_action = "repaint"
    yield done("Regenerated.")


def cmd_purge(ctx):
    ctx.drawing.push_undo()
    used_layers = {e.layer for e in ctx.drawing.entities} | {"0", ctx.drawing.current_layer}
    removed = [l for l in list(ctx.drawing.layers) if l not in used_layers]
    for l in removed:
        del ctx.drawing.layers[l]
    yield done(f"Purged {len(removed)} unused layer(s).")


def cmd_selectall(ctx):
    for e in ctx.drawing.entities:
        e.selected = True
    yield done(f"Selected all ({len(ctx.drawing.entities)}) objects.")


# ---------------------------------------------------------------- annotation / dims
# Dimension / leader geometry is built by helpers in entities.py so that
# dimensions can be ASSOCIATIVE: a dimension stores a reference to the entity
# it measures and recomputes its parts from that entity's current geometry on
# every redraw (AutoCAD-style). See entities.Annotation.recompute.

def _edit_dim_after_create(ctx, dim, msg):
    """Open the dimension value panel right after creation (SolidWorks-style
    driven dimension). If the user types a value + drive, resize the source."""
    from dim_dialog import DimEditDialog
    dlg = DimEditDialog(dim, ctx.canvas)
    if dlg.exec() == DimEditDialog.DialogCode.Accepted:
        if dlg.apply():
            ctx.drawing.solve_constraints()
            ctx.canvas.update()
            msg = f"{msg} -> driven to {dim.measurement:.3f}"
    return msg


def _line_endpoints(e):
    if e.kind == "LINE":
        return e.p1, e.p2
    if e.kind == "LWPOLYLINE" and e.verts:
        return (e.verts[0][0], e.verts[0][1]), (e.verts[-1][0], e.verts[-1][1])
    return None


def cmd_dim_linear(ctx):
    layer = ctx.drawing.current_layer
    while True:
        yield Prompt(Prompt.SELECTION, "Select a line or polyline to dimension:")
        sel = ctx.drawing.selected()
        if sel and len(sel) == 1 and sel[0].kind in ("LINE", "LWPOLYLINE"):
            src = sel[0]
            break
        ctx.canvas.status_message.emit("Select exactly ONE line/polyline (dimension must be entity-backed).")
    ends = _line_endpoints(src)
    loc = yield Prompt(Prompt.POINT, "Specify dimension line location:")
    dim = build_linear_dim(ends[0], ends[1], loc, layer, sources=[src])
    ctx.drawing.push_undo()
    ctx.drawing.add(dim)
    msg = _edit_dim_after_create(ctx, dim, f"Linear dimension: {dim.measurement:.2f}")
    yield done(msg)


def cmd_dim_radius(ctx):
    layer = ctx.drawing.current_layer
    while True:
        yield Prompt(Prompt.SELECTION, "Select a circle or arc to dimension:")
        sel = ctx.drawing.selected()
        if sel and len(sel) == 1 and sel[0].kind in ("CIRCLE", "ARC"):
            src = sel[0]
            break
        ctx.canvas.status_message.emit("Select a circle/arc (radius dimension must be entity-backed).")
    pt = yield Prompt(Prompt.POINT, "Specify point on circle/arc:")
    dim = build_radius_dim(src.center, pt, layer, diameter=False, sources=[src])
    ctx.drawing.push_undo()
    ctx.drawing.add(dim)
    msg = _edit_dim_after_create(ctx, dim, f"Radius dimension: R{dim.measurement:.2f}")
    yield done(msg)


def cmd_dim_diameter(ctx):
    layer = ctx.drawing.current_layer
    while True:
        yield Prompt(Prompt.SELECTION, "Select a circle or arc to dimension:")
        sel = ctx.drawing.selected()
        if sel and len(sel) == 1 and sel[0].kind in ("CIRCLE", "ARC"):
            src = sel[0]
            break
        ctx.canvas.status_message.emit("Select a circle/arc (diameter dimension must be entity-backed).")
    pt = yield Prompt(Prompt.POINT, "Specify point on circle/arc:")
    dim = build_radius_dim(src.center, pt, layer, diameter=True, sources=[src])
    ctx.drawing.push_undo()
    ctx.drawing.add(dim)
    msg = _edit_dim_after_create(ctx, dim, f"Diameter dimension: {dim.measurement:.2f}")
    yield done(msg)


def cmd_dim_angular(ctx):
    layer = ctx.drawing.current_layer
    while True:
        sel1 = yield Prompt(Prompt.SELECTION, "Select first line:")
        if sel1 and len(sel1) == 1 and sel1[0].kind == "LINE":
            break
        ctx.canvas.status_message.emit("Select a single LINE for the first edge.")
    l1 = sel1[0]
    while True:
        sel2 = yield Prompt(Prompt.SELECTION, "Select second line:")
        if sel2 and len(sel2) == 1 and sel2[0].kind == "LINE" and sel2[0] is not l1:
            break
        ctx.canvas.status_message.emit("Select a different single LINE for the second edge.")
    l2 = sel2[0]
    loc = yield Prompt(Prompt.POINT, "Specify dimension arc line location:")
    dim = build_angular_dim(l1, l2, loc, layer, sources=[l1, l2])
    ctx.drawing.push_undo()
    ctx.drawing.add(dim)
    msg = _edit_dim_after_create(ctx, dim, f"Angular dimension: {dim.measurement:.1f} deg")
    yield done(msg)


def cmd_dim(ctx):
    """SolidWorks-style SMART DIMENSION: one command that infers what to
    dimension from the selection.

      * one LINE / LWPOLYLINE  -> linear dimension
      * one CIRCLE / ARC       -> radius (type 'D' for diameter)
      * two LINES              -> angular dimension
    """
    layer = ctx.drawing.current_layer
    # first selection
    s1 = yield Prompt(Prompt.SELECTION, "Smart Dim - select entity (line/circle) or first line:")
    a = s1[0] if s1 else None
    if a is None:
        yield done("Smart Dim cancelled (nothing selected).")
        return

    if a.kind in ("LINE", "LWPOLYLINE"):
        # could be the first line of an angle, or a linear dim
        s2 = yield Prompt(Prompt.SELECTION,
                          "Smart Dim - select 2nd line for ANGLE, or [Enter] for LINEAR on this one:")
        b = s2[0] if s2 else None
        if b is not None and b.kind == "LINE" and b is not a:
            l1, l2 = a, b
            loc = yield Prompt(Prompt.POINT, "Specify dimension arc location:")
            dim = build_angular_dim(l1, l2, loc, layer, sources=[l1, l2])
            ctx.drawing.push_undo(); ctx.drawing.add(dim)
            msg = _edit_dim_after_create(ctx, dim, f"Angular dimension: {dim.measurement:.1f} deg")
            yield done(msg)
            return
        # linear
        ends = _line_endpoints(a)
        if ends is None:
            yield done("Smart Dim: cannot dimension this entity.")
            return
        loc = yield Prompt(Prompt.POINT, "Specify dimension line location:")
        dim = build_linear_dim(ends[0], ends[1], loc, layer, sources=[a])
        ctx.drawing.push_undo(); ctx.drawing.add(dim)
        msg = _edit_dim_after_create(ctx, dim, f"Linear dimension: {dim.measurement:.2f}")
        yield done(msg)
        return

    if a.kind in ("CIRCLE", "ARC"):
        k = yield Prompt(Prompt.TEXT,
                         "Smart Dim - [Enter] radius, or type D for DIAMETER:")
        diameter = (k or "").strip().upper().startswith("D")
        pt = yield Prompt(Prompt.POINT, "Specify point on circle/arc:")
        dim = build_radius_dim(a.center, pt, layer, diameter=diameter, sources=[a])
        ctx.drawing.push_undo(); ctx.drawing.add(dim)
        tag = "Diameter" if diameter else "Radius"
        unit = f"D{dim.measurement:.2f}" if diameter else f"R{dim.measurement:.2f}"
        msg = _edit_dim_after_create(ctx, dim, f"{tag} dimension: {unit}")
        yield done(msg)
        return

    yield done("Smart Dim: select a line, circle/arc, or two lines.")


def cmd_leader(ctx):
    pts = []
    p0 = yield Prompt(Prompt.POINT, "Specify leader start point (arrowhead):")
    pts.append(p0)
    while True:
        p = yield Prompt(Prompt.POINT, "Specify next point or [Enter to finish]:")
        if p is None:
            break
        pts.append(p)
    if len(pts) < 2:
        yield done("Need at least 2 points for a leader. Cancelled.")
        return
    t = yield Prompt(Prompt.TEXT, "Enter leader text:")
    lead = build_leader(pts, t or "", ctx.drawing.current_layer)
    ctx.drawing.push_undo()
    ctx.drawing.add(lead)
    yield done("Leader created.")


def cmd_osnap(ctx):
    modes = " ".join(sorted(ctx.canvas.snap_modes)) if ctx.canvas.snap_enabled else "OFF"
    inp = yield Prompt(Prompt.TEXT,
                       f"Snap modes [{modes}] - type END MID CEN QUA INT NEA, or OFF:")
    if not inp:
        yield done(f"Snap: {modes}")
        return
    s = inp.strip().upper()
    if s == "OFF":
        ctx.canvas.snap_enabled = False
        yield done("Object snap OFF.")
        return
    toks = s.split()
    valid = {"END", "MID", "CEN", "QUA", "INT", "NEA"}
    chosen = [t for t in toks if t in valid]
    if not chosen:
        yield done("No valid modes. Cancelled.")
        return
    ctx.canvas.snap_enabled = True
    ctx.canvas.snap_modes = set(chosen)
    yield done("Object snap modes: " + " ".join(chosen))


def cmd_ellipse(ctx):
    c = yield Prompt(Prompt.POINT, "Specify center of ellipse:")
    axis = yield Prompt(Prompt.POINT, "Specify end of major axis:")
    rx = math.hypot(axis[0] - c[0], axis[1] - c[1])
    rotation = math.atan2(axis[1] - c[1], axis[0] - c[0])
    minor = yield Prompt(Prompt.POINT, "Specify end of minor axis (distance = radius):")
    ry = math.hypot(minor[0] - c[0], minor[1] - c[1])
    e = Ellipse(c, rx, ry, rotation, layer=ctx.drawing.current_layer)
    ctx.drawing.push_undo()
    ctx.drawing.add(e)
    yield done(f"Ellipse created (rx={rx:.2f}, ry={ry:.2f}).")


def cmd_hatch(ctx):
    sel = yield Prompt(Prompt.SELECTION, "Select a closed polyline or circle to hatch:")
    if not sel:
        yield done("HATCH: nothing selected. Cancelled.")
        return
    e = sel[0]
    if e.kind == "CIRCLE":
        pts = e.to_polyline_points(24)
    elif e.kind == "LWPOLYLINE":
        pts = e.to_polyline_points(1.0)
    else:
        yield done("HATCH: select a closed polyline or circle. Cancelled.")
        return
    h = Hatch(pts, pattern="SOLID", layer=ctx.drawing.current_layer)
    ctx.drawing.push_undo()
    ctx.drawing.add(h)
    yield done("HATCH: solid fill created.")


def cmd_solid(ctx):
    pts = []
    p1 = yield Prompt(Prompt.POINT, "Specify first point:")
    pts.append(p1)
    p2 = yield Prompt(Prompt.POINT, "Specify second point:")
    pts.append(p2)
    p3 = yield Prompt(Prompt.POINT, "Specify third point:")
    p4 = yield Prompt(Prompt.POINT, "Specify fourth point or Enter for triangle:")
    pts.append(p3)
    if p4 is not None:
        pts.append(p4)
    s = Solid(pts, layer=ctx.drawing.current_layer)
    ctx.drawing.push_undo()
    ctx.drawing.add(s)
    yield done("SOLID created.")


def cmd_list(ctx):
    sel = ctx.drawing.selected() or (yield Prompt(Prompt.SELECTION, "Select objects to list:"))
    if not sel:
        yield done("LIST: nothing selected. Cancelled.")
        return
    lines = []
    for e in sel:
        lines.append(f"{e.kind}  layer={e.layer}")
        if e.kind == "LINE":
            lines.append(f"    from {e.p1} to {e.p2}")
        elif e.kind == "CIRCLE":
            lines.append(f"    center {e.center} radius {e.radius:.3f}")
        elif e.kind == "ELLIPSE":
            lines.append(f"    center {e.center} rx={e.rx:.3f} ry={e.ry:.3f}")
        elif e.kind == "ARC":
            lines.append(f"    center {e.center} r={e.radius:.3f} "
                         f"{math.degrees(e.a0):.1f}->{math.degrees(e.a1):.1f} deg")
        elif e.kind == "LWPOLYLINE":
            lines.append(f"    {len(e.verts)} vertices")
    yield done("LIST:\n" + "\n".join(lines))


def cmd_zoom_window(ctx):
    p1 = yield Prompt(Prompt.POINT, "Specify first corner:")
    p2 = yield Prompt(Prompt.POINT, "Specify opposite corner:")
    if ctx.canvas:
        ctx.canvas.zoom_window(p1, p2)
    yield done("Zoomed to window.")


def cmd_plot(ctx):
    path = yield Prompt(Prompt.TEXT, "Plot to file (PNG), e.g. C:\\plot.png:")
    if not path:
        yield done("PLOT cancelled.")
        return
    if ctx.canvas:
        ctx.canvas.plot_to_png(path)
    yield done(f"PLOT: exported view to {path}")


# ---------------------------------------------------------------- parametric / constraints

def cmd_autoconstrain(ctx):
    """SolidWorks-style: infer geometric relations from the current (or
    selected) geometry and add them as constraints."""
    n = ctx.drawing.autoconstrain_selection()
    ctx.drawing.solve_constraints()
    if ctx.canvas:
        ctx.canvas.update()
    yield done(f"AUTO-CONSTRAIN: added {n} geometric constraint(s).")


def cmd_constrain(ctx):
    """Manually add a single constraint.  Type the type, then pick entities."""
    from constraints import CONSTRAINT_TYPES
    t = yield Prompt(Prompt.TEXT,
                     "Constraint type [COINCIDENT HORIZONTAL VERTICAL PARALLEL "
                     "PERPENDICULAR EQUAL CONCENTRIC TANGENT MIDPOINT DISTANCE "
                     "RADIUS DIAMETER ANGLE]:")
    t = (t or "").strip().upper()
    if t not in CONSTRAINT_TYPES:
        yield done("Unknown constraint type. Cancelled.")
        return
    if t in ("DISTANCE", "ANGLE"):
        val = yield Prompt(Prompt.TEXT, "Dimension value:")
        try:
            val = float(val)
        except (TypeError, ValueError):
            yield done("Invalid value. Cancelled.")
            return
        var = yield Prompt(Prompt.TEXT, "Link to design variable name (or blank):")
        var = (var or "").strip().upper() or None
    elif t in ("RADIUS", "DIAMETER"):
        val = yield Prompt(Prompt.TEXT, "Radius/diameter value:")
        try:
            val = float(val)
        except (TypeError, ValueError):
            yield done("Invalid value. Cancelled.")
            return
        var = yield Prompt(Prompt.TEXT, "Link to design variable name (or blank):")
        var = (var or "").strip().upper() or None
    else:
        val = None; var = None

    cls = CONSTRAINT_TYPES[t]
    need = 2 if t in ("COINCIDENT", "PARALLEL", "PERPENDICULAR", "EQUAL",
                      "CONCENTRIC", "TANGENT", "DISTANCE", "ANGLE") else 1
    picked = []
    for k in range(need):
        ent = yield Prompt(Prompt.SELECTION, f"Select entity {k + 1} for {t}:")
        if not ent:
            yield done("Nothing selected. Cancelled.")
            return
        picked.append(ent[0])

    ctx.drawing.push_undo()
    if t == "COINCIDENT":
        con = cls(picked[0], "p1", picked[1], "p1")
    elif t in ("HORIZONTAL", "VERTICAL"):
        con = cls(picked[0])
    elif t in ("PARALLEL", "PERPENDICULAR", "EQUAL", "CONCENTRIC", "TANGENT"):
        con = cls(picked[0], picked[1])
    elif t == "MIDPOINT":
        con = cls(picked[0], picked[1], "p1")
    elif t == "DISTANCE":
        con = cls(picked[0], "p1", picked[1], "p1", value=val, var=var)
    elif t in ("RADIUS", "DIAMETER"):
        con = cls(picked[0], value=val, var=var, diameter=(t == "DIAMETER"))
    elif t == "ANGLE":
        con = cls(picked[0], picked[1], value=val, var=var)
    else:
        con = cls(*picked)
    ctx.drawing.add_constraint(con)
    res = ctx.drawing.solve_constraints()
    if ctx.canvas:
        ctx.canvas.update()
    yield done(f"{t} constraint added (residual {res:.4g}).")


def cmd_variable(ctx):
    """Create or edit a design variable (parameter) and optionally apply it to
    a dimensional constraint already linked by name."""
    name = yield Prompt(Prompt.TEXT, "Variable name (e.g. W):")
    name = (name or "").strip().upper()
    if not name:
        yield done("Cancelled.")
        return
    cur = ctx.drawing.variables.get(name)
    old = cur.value if cur else 0.0
    v = yield Prompt(Prompt.TEXT, f"Value for {name}:", default=f"{old:g}")
    try:
        v = float(v)
    except (TypeError, ValueError):
        yield done("Invalid value. Cancelled.")
        return
    ctx.drawing.push_undo()
    ctx.drawing.add_variable(name, v)
    res = ctx.drawing.solve_constraints()
    if ctx.canvas:
        ctx.canvas.update()
    yield done(f"Variable {name}={v:g} set (residual {res:.4g}).")


def cmd_rebuild(ctx):
    """Re-solve all constraints (rebuild the parametric model)."""
    res = ctx.drawing.solve_constraints()
    if ctx.canvas:
        ctx.canvas.update()
    yield done(f"REBUILD: solved with residual {res:.4g}.")


def cmd_delconstraint(ctx):
    """Remove all constraints (or future: selected ones)."""
    ctx.drawing.push_undo()
    n = len(ctx.drawing.constraints)
    ctx.drawing.clear_constraints()
    if ctx.canvas:
        ctx.canvas.update()
    yield done(f"Removed {n} constraint(s).")


# ---------------------------------------------------------------- registry

COMMANDS = {
    "LINE": cmd_line,
    "CIRCLE": cmd_circle,
    "ARC": cmd_arc,
    "PLINE": cmd_pline,
    "RECTANG": cmd_rectang,
    "POLYGON": cmd_polygon,
    "POINT": cmd_point,
    "MTEXT": cmd_text,
    "TEXT": cmd_text,
    "TEXTS": cmd_text_single,
    "DIMLINEAR": cmd_dim_linear,
    "DIMRAD": cmd_dim_radius,
    "DIMDIA": cmd_dim_diameter,
    "DIMANG": cmd_dim_angular,
    "SMARTDIM": cmd_dim,
    "DIM": cmd_dim,
    "LEADER": cmd_leader,
    "OSNAP": cmd_osnap,
    "MOVE": cmd_move,
    "COPY": cmd_copy,
    "ROTATE": cmd_rotate,
    "SCALE": cmd_scale,
    "MIRROR": cmd_mirror,
    "ERASE": cmd_erase,
    "OFFSET": cmd_offset,
    "FILLET": cmd_fillet,
    "CHAMFER": cmd_chamfer,
    "TRIM": cmd_trim,
    "EXTEND": cmd_extend,
    "STRETCH": cmd_stretch,
    "EXPLODE": cmd_explode,
    "JOIN": cmd_join,
    "BREAK": cmd_break,
    "ARRAY": cmd_array_rect,
    "UNDO": cmd_undo,
    "REDO": cmd_redo,
    "DIST": cmd_dist,
    "MEASURE": cmd_dist,
    "AREA": cmd_area,
    "LIST": cmd_list,
    "LAYER": cmd_layer,
    "REGEN": cmd_regen,
    "REDRAW": cmd_regen,
    "PURGE": cmd_purge,
    "SELECTALL": cmd_selectall,
    "ELLIPSE": cmd_ellipse,
    "HATCH": cmd_hatch,
    "SOLID": cmd_solid,
    "BREAK": cmd_break,
    "EXTEND": cmd_extend,
    "ZOOM_WIN": cmd_zoom_window,
    "ZOOMWINDOW": cmd_zoom_window,
    "PROPERTIES": cmd_list,
    "PLOT": cmd_plot,
    # parametric / constraints
    "AUTOCONSTRAIN": cmd_autoconstrain,
    "FULLYDEFINE": cmd_autoconstrain,
    "CONSTRAIN": cmd_constrain,
    "ADDCONSTRAINT": cmd_constrain,
    "VARIABLE": cmd_variable,
    "PARAM": cmd_variable,
    "REBUILD": cmd_rebuild,
    "DELCONSTRAINT": cmd_delconstraint,
    "DELPARAM": cmd_delconstraint,
}


class CommandContext:
    def __init__(self, drawing, canvas=None):
        self.drawing = drawing
        self.canvas = canvas
        self.canvas_action = None
