"""
gcode.py
Direct port of Sidharth's GCODEGEN_.lsp (waterjet/laser/plasma 2D profile
G-code generator) to Python. Function names/structure intentionally mirror
the LISP so it's easy to cross-check against the original:
  VSub/VAdd/VScale/VLen/VUnit/VPerp
  WriteSegment, BulgeToArcPts
  EntityToVerts / EntityClosed  (adapted to our Entity classes)
  RotateVertsToStart, LinearizeVerts/LinearizeSegment
  LeadPoint/LeadOutPoint/LeadInArc/LeadOutArc
  WritePath, WritePathContinuous, BuildPassList
Output G-code is numerically identical in structure to the DraftSight LSP.
"""
import math


def VSub(a, b): return (a[0] - b[0], a[1] - b[1])
def VAdd(a, b): return (a[0] + b[0], a[1] + b[1])
def VScale(a, s): return (a[0] * s, a[1] * s)
def VLen(a): return math.hypot(a[0], a[1])
def VUnit(a):
    l = VLen(a)
    return VScale(a, 1.0 / l) if l > 1e-9 else (1.0, 0.0)
def VPerp(a): return (-a[1], a[0])


def rtos(v, dec=3):
    return f"{v:.{dec}f}"


class GCodeParams:
    def __init__(self):
        self.feed = 800.0
        self.rpm = 12000.0
        self.safez = 10.0
        self.cutz = -2.0
        self.passdepth = 0.0
        self.plungef = 200.0
        self.tooldia = 6.0
        self.toolnum = 0
        self.wcs = "G54"
        self.coolant = False
        self.homex = 0.0
        self.homey = 0.0
        self.comp = 0          # 0 none, 1 G41 left, 2 G42 right
        self.strategy = 0      # 0 one-way retract, 1 zig-zag continuous
        self.leadtype = 0      # 0 none, 1 linear, 2 arc
        self.leadlen = 5.0
        self.leadangle = 45.0
        self.interp_on = False
        self.interp_step = 0.1
        self.origin = (0.0, 0.0)
        self.start_pt = None   # world coords or None (auto)
        self.reverse = False
        self.kerf = 0.0        # kerf / cut width [mm] (0 = none / controller comp only)
        self.pierce_dwell = 0.0  # pierce dwell time [s]
        self.overcut = 0.0     # overcut past start on closed loops [mm]
        self.sequence_inner_first = False  # cut contained contours before parents
        self.tabs_count = 0    # number of tabs/bridges (0 = none)
        self.tabs_width = 2.0  # tab width [mm]


def entity_to_verts_raw(ent):
    """Returns list of (point, bulge) tuples, same semantics as the LSP."""
    if ent.kind == "LINE":
        return [(ent.p1, 0.0), (ent.p2, 0.0)]
    if ent.kind == "ARC":
        sa, ea = ent.start_ang, ent.end_ang
        inc = ea - sa
        if inc < 0.0:
            inc += 2 * math.pi
        bulge = math.tan(inc / 4.0)
        cx, cy = ent.center
        sp = (cx + ent.radius * math.cos(sa), cy + ent.radius * math.sin(sa))
        ep = (cx + ent.radius * math.cos(ea), cy + ent.radius * math.sin(ea))
        return [(sp, bulge), (ep, 0.0)]
    if ent.kind == "CIRCLE":
        cx, cy = ent.center
        r = ent.radius
        sp = (cx + r, cy)
        v1 = (cx - r, cy)
        return [(sp, 1.0), (v1, 1.0), (sp, 0.0)]
    if ent.kind == "LWPOLYLINE":
        return [((v[0], v[1]), v[2]) for v in ent.verts]
    return None


def shift_verts(verts, origin):
    ox, oy = origin
    return [((p[0] - ox, p[1] - oy), b) for p, b in verts]


def entity_to_verts(ent, origin):
    raw = entity_to_verts_raw(ent)
    if raw is None:
        return None
    return shift_verts(raw, origin)


def entity_closed(ent):
    if ent.kind == "CIRCLE":
        return True
    if ent.kind == "LWPOLYLINE":
        return ent.closed
    return False


def reverse_verts(verts):
    pts = [v[0] for v in verts]
    bulges = [v[1] for v in verts]
    revpts = list(reversed(pts))
    revb = list(reversed(bulges))
    nb = [-b for b in revb[1:]] + [0.0]
    return list(zip(revpts, nb))


def rotate_verts_to_start(verts, closed, pt):
    if pt and closed and len(verts) > 2:
        n = len(verts)
        best, bestd = 0, 1e18
        for i in range(n):
            d = math.hypot(verts[i][0][0] - pt[0], verts[i][0][1] - pt[1])
            if d < bestd:
                bestd, best = d, i
        return [verts[(best + k) % n] for k in range(n)]
    return verts


def linearize_segment(p1, p2, bulge, step):
    if not step or step <= 0.0:
        step = 1.0
    if not bulge or abs(bulge) < 1e-8:
        d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        nseg = max(1, int(0.9999 + d / step))
        return [(p1[0] + (p2[0] - p1[0]) * i / nseg,
                  p1[1] + (p2[1] - p1[1]) * i / nseg) for i in range(nseg + 1)]
    d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    theta = 4.0 * math.atan(bulge)
    r = (d * 0.5) / math.sin(theta / 2.0)
    mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    ux, uy = (p2[0] - p1[0]) / d, (p2[1] - p1[1]) / d
    h = math.sqrt(max(0.0, r * r - (d / 2.0) ** 2)) * (1.0 if r > 0.0 else -1.0)
    cx, cy = mid[0] + (-uy) * h, mid[1] + ux * h
    rad = math.hypot(cx - p1[0], cy - p1[1])
    arclen = rad * abs(theta)
    nseg = max(1, int(0.9999 + arclen / step))
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    return [(cx + rad * math.cos(a1 + theta * i / nseg),
             cy + rad * math.sin(a1 + theta * i / nseg)) for i in range(nseg + 1)]


def linearize_verts(verts, closed, step):
    n = len(verts)
    if n < 2:
        return verts
    limit = n if closed else n - 1
    out = []
    for i in range(limit):
        v1, v2 = verts[i], verts[(i + 1) % n]
        segpts = linearize_segment(v1[0], v2[0], v1[1], step)
        for k in range(len(segpts) - 1):
            out.append((segpts[k], 0.0))
    if not closed:
        out.append((verts[-1][0], 0.0))
    return out


def bulge_to_arc_pts(p1, p2, bulge, nseg):
    if not bulge or abs(bulge) < 1e-8:
        return [p1, p2]
    d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    theta = 4.0 * math.atan(bulge)
    r = (d * 0.5) / math.sin(theta / 2.0)
    mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    ux, uy = (p2[0] - p1[0]) / d, (p2[1] - p1[1]) / d
    h = math.sqrt(max(0.0, r * r - (d / 2.0) ** 2)) * (1.0 if r > 0.0 else -1.0)
    cx, cy = mid[0] + (-uy) * h, mid[1] + ux * h
    rad = math.hypot(p1[0] - cx, p1[1] - cy)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    return [(cx + rad * math.cos(a1 + theta * i / nseg),
             cy + rad * math.sin(a1 + theta * i / nseg)) for i in range(nseg + 1)]


def write_segment(out, p1, p2, bulge, feed, prefix=""):
    if not bulge or abs(bulge) < 1e-8:
        out.append(f"{prefix}G01 X{rtos(p2[0])} Y{rtos(p2[1])} F{rtos(feed,0)}")
        return
    d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    theta = 4.0 * math.atan(bulge)
    r = (d * 0.5) / math.sin(theta / 2.0)
    mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    ux, uy = (p2[0] - p1[0]) / d, (p2[1] - p1[1]) / d
    h = math.sqrt(max(0.0, r * r - (d / 2.0) ** 2)) * (1.0 if r > 0.0 else -1.0)
    cx, cy = mid[0] + (-uy) * h, mid[1] + ux * h
    code = "G03" if bulge > 0.0 else "G02"
    out.append(f"{prefix}{code} X{rtos(p2[0])} Y{rtos(p2[1])} "
               f"I{rtos(cx - p1[0])} J{rtos(cy - p1[1])} F{rtos(feed,0)}")


def write_ramp_segment(out, p1, p2, bulge, feed, zl):
    if not bulge or abs(bulge) < 1e-8:
        out.append(f"G01 X{rtos(p2[0])} Y{rtos(p2[1])} Z{rtos(zl)} F{rtos(feed,0)}")
    else:
        out.append(f"G01 Z{rtos(zl)} F{rtos(feed,0)}")
        write_segment(out, p1, p2, bulge, feed, "")


def lead_point(base, tangent, length, angle_deg):
    rad = math.radians(angle_deg)
    d = (-tangent[0], -tangent[1])
    rotated = (math.cos(rad) * d[0] - math.sin(rad) * d[1],
               math.sin(rad) * d[0] + math.cos(rad) * d[1])
    return VAdd(base, VScale(rotated, length))


def lead_out_point(base, tangent, length, angle_deg):
    rad = math.radians(angle_deg)
    rotated = (math.cos(rad) * tangent[0] - math.sin(rad) * tangent[1],
               math.sin(rad) * tangent[0] + math.cos(rad) * tangent[1])
    return VAdd(base, VScale(rotated, length))


def arc_lead_center(base, tangent, radius, turn_sign):
    return VAdd(base, VScale(VPerp(tangent), turn_sign * radius))


def pt_angle(pt, center):
    return math.atan2(pt[1] - center[1], pt[0] - center[0])


def lead_in_arc(p0, tanS, radius, sweep_deg, turn_sign):
    center = arc_lead_center(p0, tanS, radius, turn_sign)
    a0 = pt_angle(p0, center)
    sweep = math.radians(sweep_deg)
    a_lead = a0 - turn_sign * sweep
    lead_pt = (center[0] + radius * math.cos(a_lead), center[1] + radius * math.sin(a_lead))
    bulge = turn_sign * math.tan(sweep / 4.0)
    return lead_pt, bulge


def lead_out_arc(pn, tanE, radius, sweep_deg, turn_sign):
    center = arc_lead_center(pn, tanE, radius, turn_sign)
    a0 = pt_angle(pn, center)
    sweep = math.radians(sweep_deg)
    a_lead = a0 + turn_sign * sweep
    lead_pt = (center[0] + radius * math.cos(a_lead), center[1] + radius * math.sin(a_lead))
    bulge = turn_sign * math.tan(sweep / 4.0)
    return lead_pt, bulge


def build_pass_list(cutz, passdepth):
    if not passdepth or passdepth <= 0.0:
        return [cutz]
    levels = []
    z = 0.0
    while z > cutz:
        z -= passdepth
        if z < cutz:
            z = cutz
        levels.append(z)
    return levels or [cutz]


def _contour_centroid(ent):
    pts = ent.to_polyline_points(seg_len=2.0)
    if not pts:
        return (0.0, 0.0)
    n = len(pts)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def _point_in_entity(pt, ent):
    """Even-odd ray-cast point-in-polygon test for a closed entity."""
    if not entity_closed(ent):
        return False
    poly = ent.to_polyline_points(seg_len=1.0)
    if len(poly) < 3:
        return False
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _inner_first_order(entities):
    """Return entities ordered so contained (inner) closed contours cut
    before the closed contours that contain them; open entities last."""
    closed = [e for e in entities if entity_closed(e)]
    openc = [e for e in entities if not entity_closed(e)]

    def is_inner(e):
        c = _contour_centroid(e)
        for o in closed:
            if o is e:
                continue
            if _point_in_entity(c, o):
                return True
        return False

    inners = [e for e in closed if is_inner(e)]
    outers = [e for e in closed if not is_inner(e)]
    return inners + outers + openc


def _emit_contour(out, lin, cutz, params):
    """Emit a linearized closed/open contour as G01 cuts, inserting pen-up
    'tabs' (bridges) at evenly spaced arc-length intervals and optionally
    extending past the start (overcut) so closed loops fully close."""
    pts = list(lin)
    if params.overcut > 0 and len(pts) >= 2:
        d = VUnit(VSub(pts[1], pts[0]))
        pts.append(VAdd(pts[0], VScale(d, params.overcut)))
    if len(pts) < 2:
        return
    segL = []
    total = 0.0
    for i in range(len(pts) - 1):
        L = VLen(VSub(pts[i + 1], pts[i]))
        segL.append(L)
        total += L
    if params.tabs_count > 0 and total > 1e-9:
        spacing = total / params.tabs_count
        half = min(params.tabs_width / 2.0, spacing / 2.0 - 1e-6)
        centers = [spacing * (i + 0.5) for i in range(params.tabs_count)]
        pen_down = True
        cum = 0.0
        for i in range(len(pts) - 1):
            s0 = cum
            s1 = cum + segL[i]
            mid = (s0 + s1) / 2.0
            in_tab = any(abs(mid - c) <= half for c in centers)
            cum = s1
            if in_tab and pen_down:
                out.append(f"G00 Z{rtos(params.safez)}")
                pen_down = False
            elif (not in_tab) and (not pen_down):
                out.append(f"G01 Z{rtos(cutz)} F{rtos(params.plungef, 0)}")
                pen_down = True
            a, b = pts[i], pts[i + 1]
            if pen_down:
                out.append(f"G01 X{rtos(b[0])} Y{rtos(b[1])} F{rtos(params.feed, 0)}")
            else:
                out.append(f"G00 X{rtos(b[0])} Y{rtos(b[1])}")
        if not pen_down:
            out.append(f"G01 Z{rtos(cutz)} F{rtos(params.plungef, 0)}")
    else:
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            out.append(f"G01 X{rtos(b[0])} Y{rtos(b[1])} F{rtos(params.feed, 0)}")


def write_path(out, verts, closed, params, zl=None):
    wverts = reverse_verts(verts) if params.reverse else verts
    n = len(wverts)
    if n < 2:
        return
    cutz = zl if zl is not None else params.cutz
    p0, p1 = wverts[0][0], wverts[1][0]
    tanS = VUnit(VSub(p1, p0))
    pnm1, pn = wverts[n - 2][0], wverts[n - 1][0]
    tanE = VUnit(VSub(pn, pnm1))
    dcode = params.toolnum if params.toolnum > 0 else 1
    comp_code = {1: "G41", 2: "G42"}.get(params.comp)
    turn_sign = -1.0 if params.comp == 2 else 1.0

    lead_in_pt = lead_in_bulge = lead_out_pt = lead_out_bulge = None
    if params.leadtype == 1 and params.leadlen > 0.0:
        lead_in_pt = lead_point(p0, tanS, params.leadlen, params.leadangle)
        lead_out_pt = lead_out_point(pn, tanE, params.leadlen, params.leadangle)
        lead_in_bulge = lead_out_bulge = 0.0
    elif params.leadtype == 2 and params.leadlen > 0.0:
        lead_in_pt, lead_in_bulge = lead_in_arc(p0, tanS, params.leadlen, params.leadangle, turn_sign)
        lead_out_pt, lead_out_bulge = lead_out_arc(pn, tanE, params.leadlen, params.leadangle, turn_sign)

    if lead_in_pt:
        out.append(f"G00 X{rtos(lead_in_pt[0])} Y{rtos(lead_in_pt[1])} Z{rtos(params.safez)}")
    else:
        out.append(f"G00 X{rtos(p0[0])} Y{rtos(p0[1])} Z{rtos(params.safez)}")
    out.append(f"G01 Z{rtos(cutz)} F{rtos(params.plungef, 0)}")
    if params.pierce_dwell > 0:
        out.append(f"G04 P{rtos(params.pierce_dwell, 2)}")

    if lead_in_pt:
        prefix = f"{comp_code} D{dcode} " if comp_code else ""
        write_segment(out, lead_in_pt, p0, lead_in_bulge, params.feed, prefix)
    elif comp_code:
        out.append(f"{comp_code} D{dcode}")

    if params.tabs_count > 0 and closed:
        # linearize the contour and emit it with tab (pen-up) bridges
        step = params.interp_step if params.interp_step > 0 else 1.0
        lin = [v[0] for v in linearize_verts(wverts, True, step)]
        _emit_contour(out, lin, cutz, params)
    else:
        for i in range(n - 1):
            v1, v2 = wverts[i], wverts[i + 1]
            write_segment(out, v1[0], v2[0], v1[1], params.feed, "")
        if closed:
            v1, v2 = wverts[n - 1], wverts[0]
            write_segment(out, v1[0], v2[0], v1[1], params.feed, "")
            if params.overcut > 0:
                d = VUnit(VSub(wverts[1][0], wverts[0][0]))
                op = VAdd(wverts[0][0], VScale(d, params.overcut))
                write_segment(out, wverts[0][0], op, 0.0, params.feed, "")

    if lead_out_pt:
        write_segment(out, pn, lead_out_pt, lead_out_bulge, params.feed, "")
    if comp_code:
        out.append("G40")
    out.append(f"G00 Z{rtos(params.safez)}")


def write_path_continuous(out, verts, closed, params, zlevels):
    n = len(verts)
    if n < 2:
        return
    p0 = verts[0][0]
    dcode = params.toolnum if params.toolnum > 0 else 1
    comp_code = {1: "G41", 2: "G42"}.get(params.comp)
    out.append(f"G00 X{rtos(p0[0])} Y{rtos(p0[1])} Z{rtos(params.safez)}")
    if comp_code:
        out.append(f"{comp_code} D{dcode}")

    for pass_i, zl in enumerate(zlevels):
        wverts = reverse_verts(verts) if pass_i % 2 == 1 else verts
        n2 = len(wverts)
        for i in range(n2 - 1):
            v1, v2 = wverts[i], wverts[i + 1]
            if i == 0:
                write_ramp_segment(out, v1[0], v2[0], v1[1], params.feed, zl)
            else:
                write_segment(out, v1[0], v2[0], v1[1], params.feed, "")
        if closed:
            v1, v2 = wverts[n2 - 1], wverts[0]
            write_segment(out, v1[0], v2[0], v1[1], params.feed, "")

    if comp_code:
        out.append("G40")
    out.append(f"G00 Z{rtos(params.safez)}")


def process_entity(ent, out, params, zl):
    verts = entity_to_verts(ent, params.origin)
    if not verts:
        return False
    closed = entity_closed(ent)
    start = None
    if params.start_pt:
        start = (params.start_pt[0] - params.origin[0], params.start_pt[1] - params.origin[1])
    verts = rotate_verts_to_start(verts, closed, start)
    if params.interp_on:
        verts = linearize_verts(verts, closed, params.interp_step)
    write_path(out, verts, closed, params, zl)
    return True


def generate_gcode(entities, params: GCodeParams):
    """entities: list of Entity objects (LINE/ARC/CIRCLE/LWPOLYLINE supported,
    same as the LSP's GeomFilter). Returns (gcode_text, warnings)."""
    out = []
    warnings = []
    supported = []
    annotations = []
    for e in entities:
        if e.kind in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE"):
            supported.append(e)
        elif e.kind in ("TEXT", "POINT"):
            annotations.append(e)
        else:
            warnings.append(f"Skipped unsupported entity type: {e.kind}")

    out.append("%")
    out.append("(GCODEGEN.PY - ported from GCODEGEN_.lsp)")
    out.append(f"(TOOL DIA {rtos(params.tooldia)} mm)")
    if params.kerf > 0:
        out.append(f"(KERF WIDTH {rtos(params.kerf)} mm)")
    if params.overcut > 0:
        out.append(f"(OVERCUT {rtos(params.overcut)} mm)")
    if params.tabs_count > 0:
        out.append(f"(TABS {params.tabs_count} x {rtos(params.tabs_width)} mm)")
    out.append("G21 G90 G17 G94")
    out.append(params.wcs)
    if params.toolnum > 0:
        out.append(f"T{params.toolnum} M06")
    out.append(f"M03 S{rtos(params.rpm,0)}")
    if params.coolant:
        out.append("M08")
    out.append(f"G00 X{rtos(params.homex)} Y{rtos(params.homey)} Z{rtos(params.safez)}")

    if params.sequence_inner_first:
        supported = _inner_first_order(supported)
    zlevels = build_pass_list(params.cutz, params.passdepth)

    if params.strategy == 1:
        out.append("(--- ZIG-ZAG CONTINUOUS RAMP ---)")
        for ent in supported:
            verts = entity_to_verts(ent, params.origin)
            if not verts:
                continue
            closed = entity_closed(ent)
            start = None
            if params.start_pt:
                start = (params.start_pt[0] - params.origin[0], params.start_pt[1] - params.origin[1])
            verts = rotate_verts_to_start(verts, closed, start)
            if params.interp_on:
                verts = linearize_verts(verts, closed, params.interp_step)
            write_path_continuous(out, verts, closed, params, zlevels)
    else:
        for zl in zlevels:
            out.append(f"(--- PASS Z{rtos(zl)} ---)")
            for ent in supported:
                process_entity(ent, out, params, zl)

    out.append("(--- ANNOTATIONS: TEXT / POINT markers ---)")
    for e in annotations:
        if e.kind == "TEXT":
            X = e.pos[0] - params.origin[0]
            Y = e.pos[1] - params.origin[1]
            out.append(f'(TEXT: "{e.text}" @ X{rtos(X)} Y{rtos(Y)} H{rtos(e.height)})')
            out.append(f"G00 X{rtos(X)} Y{rtos(Y)}")
        elif e.kind == "POINT":
            X = e.pos[0] - params.origin[0]
            Y = e.pos[1] - params.origin[1]
            out.append(f"(POINT @ X{rtos(X)} Y{rtos(Y)})")
            out.append(f"G00 X{rtos(X)} Y{rtos(Y)}")

    if params.coolant:
        out.append("M09")
    out.append("M05")
    out.append(f"G00 Z{rtos(params.safez)}")
    out.append(f"G00 X{rtos(params.homex)} Y{rtos(params.homey)}")
    out.append("M30")
    out.append("%")

    return "\n".join(out) + "\n", warnings


# ---------------------------------------------------------------------------
# Controller-neutral event emission (used by the post-processor system)
# ---------------------------------------------------------------------------

def emit_path_to_events(entities, params: GCodeParams):
    """Produce a controller-neutral list of toolpath EVENT tuples from the
    geometry.  The post-processor (posts.py) turns these into machine G-code.
    This keeps ALL machine-specific syntax out of the geometry logic."""
    events = []
    warnings = []

    supported = []
    annotations = []
    for e in entities:
        if e.kind in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE"):
            supported.append(e)
        elif e.kind in ("TEXT", "POINT"):
            annotations.append(e)
        else:
            warnings.append(f"Skipped unsupported entity type: {e.kind}")

    events.append(("PROGRAM_START",))
    events.append(("COMMENT", "GCODEGEN.PY - ported from GCODEGEN_.lsp"))
    events.append(("COMMENT", f"TOOL DIA {params.tooldia} mm"))
    if params.kerf > 0:
        events.append(("COMMENT", f"KERF WIDTH {params.kerf} mm"))
    if params.overcut > 0:
        events.append(("COMMENT", f"OVERCUT {params.overcut} mm"))
    if params.tabs_count > 0:
        events.append(("COMMENT", f"TABS {params.tabs_count} x {params.tabs_width} mm"))
    events.append(("WCS", params.wcs))
    if params.toolnum > 0:
        events.append(("TOOLCHANGE", params.toolnum))
    events.append(("SPIN_ON", params.rpm, True))
    if params.coolant:
        events.append(("COOL_ON",))
    events.append(("RAPID", params.homex, params.homey, params.safez))

    if params.sequence_inner_first:
        supported = _inner_first_order(supported)
    zlevels = build_pass_list(params.cutz, params.passdepth)

    for zl in zlevels:
        events.append(("COMMENT", f"--- PASS Z{rtos(zl)} ---"))
        for ent in supported:
            verts = entity_to_verts(ent, params.origin)
            if not verts:
                continue
            closed = entity_closed(ent)
            start = None
            if params.start_pt:
                start = (params.start_pt[0] - params.origin[0],
                         params.start_pt[1] - params.origin[1])
            verts = rotate_verts_to_start(verts, closed, start)
            if params.interp_on:
                verts = linearize_verts(verts, closed, params.interp_step)
            _emit_path_events(events, verts, closed, params, zl)

    for e in annotations:
        if e.kind == "TEXT":
            X = e.pos[0] - params.origin[0]; Y = e.pos[1] - params.origin[1]
            events.append(("COMMENT", f'TEXT: "{e.text}" @ X{X:.3f} Y{Y:.3f} H{e.height}'))
            events.append(("RAPID", X, Y, params.safez))
        elif e.kind == "POINT":
            X = e.pos[0] - params.origin[0]; Y = e.pos[1] - params.origin[1]
            events.append(("COMMENT", f"POINT @ X{X:.3f} Y{Y:.3f}"))
            events.append(("RAPID", X, Y, params.safez))

    if params.coolant:
        events.append(("COOL_OFF",))
    events.append(("SPIN_OFF",))
    events.append(("RAPID_HOME", params.safez, params.homex, params.homey))
    events.append(("PROGRAM_END",))

    return events, warnings


def _emit_path_events(events, verts, closed, params, zl=None):
    wverts = reverse_verts(verts) if params.reverse else verts
    n = len(wverts)
    if n < 2:
        return
    cutz = zl if zl is not None else params.cutz
    p0, p1 = wverts[0][0], wverts[1][0]
    tanS = VUnit(VSub(p1, p0))
    pnm1, pn = wverts[n - 2][0], wverts[n - 1][0]
    tanE = VUnit(VSub(pn, pnm1))
    dcode = params.toolnum if params.toolnum > 0 else 1
    comp_code = {1: "G41", 2: "G42"}.get(params.comp)
    turn_sign = -1.0 if params.comp == 2 else 1.0

    lead_in_pt = lead_in_bulge = lead_out_pt = lead_out_bulge = None
    if params.leadtype == 1 and params.leadlen > 0.0:
        lead_in_pt = lead_point(p0, tanS, params.leadlen, params.leadangle)
        lead_out_pt = lead_out_point(pn, tanE, params.leadlen, params.leadangle)
        lead_in_bulge = lead_out_bulge = 0.0
    elif params.leadtype == 2 and params.leadlen > 0.0:
        lead_in_pt, lead_in_bulge = lead_in_arc(p0, tanS, params.leadlen,
                                                 params.leadangle, turn_sign)
        lead_out_pt, lead_out_bulge = lead_out_arc(pn, tanE, params.leadlen,
                                                    params.leadangle, turn_sign)

    if lead_in_pt:
        events.append(("RAPID", lead_in_pt[0], lead_in_pt[1], params.safez))
    else:
        events.append(("RAPID", p0[0], p0[1], params.safez))
    events.append(("PLUNGE", cutz, params.plungef))
    if params.pierce_dwell > 0:
        events.append(("DWELL", params.pierce_dwell))
    if lead_in_pt:
        if comp_code:
            events.append(("COMP_ON", comp_code, dcode))
        _emit_arc_or_line(events, lead_in_pt, p0, lead_in_bulge, params)
    elif comp_code:
        events.append(("COMP_ON", comp_code, dcode))

    for i in range(n - 1):
        v1, v2 = wverts[i], wverts[i + 1]
        _emit_arc_or_line(events, v1[0], v2[0], v1[1], params)
    if closed:
        v1, v2 = wverts[n - 1], wverts[0]
        _emit_arc_or_line(events, v1[0], v2[0], v1[1], params)
        if params.overcut > 0:
            d = VUnit(VSub(wverts[1][0], wverts[0][0]))
            op = VAdd(wverts[0][0], VScale(d, params.overcut))
            events.append(("CUT", op[0], op[1], params.feed, 0.0, 0.0, False))

    if lead_out_pt:
        _emit_arc_or_line(events, pn, lead_out_pt, lead_out_bulge, params)
    if comp_code:
        events.append(("COMP_OFF",))
    events.append(("RAPID", pn[0], pn[1], params.safez))


def _emit_arc_or_line(events, p1, p2, bulge, params):
    if bulge and abs(bulge) >= 1e-8:
        d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        theta = 4.0 * math.atan(bulge)
        r = (d * 0.5) / math.sin(theta / 2.0)
        mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        ux, uy = (p2[0] - p1[0]) / d, (p2[1] - p1[1]) / d
        h = math.sqrt(max(0.0, r * r - (d / 2.0) ** 2)) * (1.0 if r > 0.0 else -1.0)
        cx, cy = mid[0] + (-uy) * h, mid[1] + ux * h
        cw = bulge < 0.0
        events.append(("CUTARC", p2[0], p2[1], cx - p1[0], cy - p1[1],
                       params.feed, cw))
    else:
        events.append(("CUT", p2[0], p2[1], params.feed, 0.0, 0.0, False))
