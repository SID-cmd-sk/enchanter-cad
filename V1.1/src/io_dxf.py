"""
io_dxf.py
Load/save drawings. Native DXF via ezdxf. DWG is handled by shelling out
to the free Open Design Alliance "ODA File Converter" (a standalone .exe
you install once - https://www.opendesign.com/guestfiles/oda_file_converter).
This is the same approach every non-Autodesk CAD tool uses for DWG, since
the DWG format itself is only fully licensed to Autodesk/ODA members.

If ODA File Converter isn't found, DWG open/save fails with a clear message
telling the user where to get it - it does NOT silently corrupt data.

Import is intentionally permissive: foreign CAD packages (AutoCAD, SolidWorks,
Fusion, QCAD, LibreCAD, FreeCAD, ...) routinely store geometry as POLYLINE,
SPLINE, ELLIPSE, MTEXT or inside BLOCK / INSERT references. We use
ezdxf.disassemble.recursive_decompose() to blow nested blocks/inserts open
and get one flat stream of WCS entities, then convert every primitive we
recognise. Anything we can't make sense of is skipped (not fatal) so a "bad"
file still brings in whatever usable geometry it has.
"""
import os
import math
import shutil
import subprocess
import tempfile
import ezdxf

from entities import (Drawing, Line, Circle, Arc, LWPolyline, TextEntity,
                      Point, Ellipse, Hatch, Solid,
                      Dimension, Leader, build_linear_dim, build_radius_dim,
                      build_angular_dim, build_leader)

ODA_CONVERTER_CANDIDATES = [
    r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
    r"C:\Program Files\ODA File Converter\ODAFileConverter.exe",
    "ODAFileConverter",
]


def find_oda_converter():
    for c in ODA_CONVERTER_CANDIDATES:
        if os.path.isfile(c):
            return c
        found = shutil.which(c)
        if found:
            return found
    return None


class DWGSupportError(Exception):
    pass


def dwg_to_dxf(dwg_path):
    exe = find_oda_converter()
    if not exe:
        raise DWGSupportError(
            "DWG support requires the free ODA File Converter.\n"
            "Download: https://www.opendesign.com/guestfiles/oda_file_converter\n"
            "Install it, then retry opening this DWG."
        )
    src_dir = os.path.dirname(os.path.abspath(dwg_path))
    tmp_out = tempfile.mkdtemp(prefix="cadapp_dwg_")
    # ODAFileConverter <in_dir> <out_dir> <out_ver> <out_type> <recurse> <audit> [filter]
    args = [exe, src_dir, tmp_out, "ACAD2018", "DXF", "0", "1", os.path.basename(dwg_path)]
    subprocess.run(args, check=True, timeout=120)
    base = os.path.splitext(os.path.basename(dwg_path))[0]
    out_path = os.path.join(tmp_out, base + ".dxf")
    if not os.path.isfile(out_path):
        raise DWGSupportError("ODA File Converter did not produce output DXF.")
    return out_path


def dxf_to_dwg(dxf_path, dwg_target_path, version="ACAD2018"):
    exe = find_oda_converter()
    if not exe:
        raise DWGSupportError(
            "DWG support requires the free ODA File Converter.\n"
            "Download: https://www.opendesign.com/guestfiles/oda_file_converter"
        )
    src_dir = os.path.dirname(os.path.abspath(dxf_path))
    tmp_out = tempfile.mkdtemp(prefix="cadapp_dwgout_")
    args = [exe, src_dir, tmp_out, version, "DWG", "0", "1", os.path.basename(dxf_path)]
    subprocess.run(args, check=True, timeout=120)
    base = os.path.splitext(os.path.basename(dxf_path))[0]
    produced = os.path.join(tmp_out, base + ".dwg")
    if not os.path.isfile(produced):
        raise DWGSupportError("ODA File Converter did not produce output DWG.")
    shutil.copy(produced, dwg_target_path)


# --------------------------------------------------------------------------- load
def load_drawing(path):
    ext = os.path.splitext(path)[1].lower()
    dxf_path = path
    if ext == ".dwg":
        dxf_path = dwg_to_dxf(path)
    try:
        doc = ezdxf.readfile(dxf_path)
    except ezdxf.DXFStructureError:
        # file is damaged / non-standard: try the recovery reader so we still
        # pull out as much geometry as possible instead of failing hard.
        doc, _auditor = ezdxf.recover.readfile(dxf_path)
    msp = doc.modelspace()
    subclass_map = _parse_dim_subclasses(dxf_path)
    drawing = Drawing()
    for layer in doc.layers:
        drawing.layers[layer.dxf.name] = {
            "color": layer.dxf.color, "on": True, "frozen": False
        }
    imported = 0
    skipped = 0
    for e in msp:
        # manual recursive walk: expands INSERT/BLOCK references into their
        # transformed geometry and converts every leaf primitive. Done by hand
        # (instead of ezdxf.disassemble.recursive_decompose) because that
        # routine calls virtual_entities() on un-rendered DIMENSION/LEADER
        # entities, which raises and aborts the entire import for many
        # third-party DXF files - exactly the "nothing comes in" symptom.
        for ent in _expand(e):
            try:
                conv = _from_dxf_entity(ent, subclass_map.get(ent.dxf.handle))
            except Exception:
                conv = None
            if conv is not None:
                if isinstance(conv, list):
                    for c in conv:
                        if c is not None:
                            drawing.add(c); imported += 1
                else:
                    drawing.add(conv); imported += 1
            else:
                skipped += 1
    drawing.filepath = path
    drawing._import_report = (imported, skipped)
    return drawing


def _expand(entity):
    """Yield the input entity, or - if it is a block reference (INSERT) - the
    fully transformed contents of the referenced block, recursing into nested
    blocks. A failure on one reference never propagates."""
    t = entity.dxftype()
    if t in ("INSERT", "ATTDEF", "ATTRIB"):
        try:
            for ve in entity.virtual_entities():
                yield from _expand(ve)
        except Exception:
            return
    else:
        yield entity


def _parse_dim_subclasses(dxf_path):
    """Map each DIMENSION entity's handle -> specific subclass marker
    (AcDb2LineAngularDimension, AcDbRadialDimension, ...). ezdxf does not
    expose the subclass, so read it from the raw DXF text."""
    result = {}
    try:
        lines = open(dxf_path, "r", errors="ignore").read().splitlines()
    except Exception:
        return result
    n = len(lines)
    i = 0
    while i < n:
        if lines[i].strip() == "0" and i + 1 < n and lines[i + 1].strip() == "DIMENSION":
            handle = None
            subclass = None
            j = i + 2
            while j < n:
                code = lines[j].strip()
                if code == "0":
                    break
                val = lines[j + 1].strip() if j + 1 < n else ""
                if code == "5":
                    handle = val
                elif code == "100" and "Dimension" in val:
                    subclass = val
                j += 2
            if handle is not None:
                result[handle] = subclass
            i = j
        else:
            i += 1
    return result


def _from_dxf_entity(e, subclass=None):
    t = e.dxftype()
    layer = e.dxf.layer
    try:
        if t == "LINE":
            return Line((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y), layer=layer)
        if t == "CIRCLE":
            return Circle((e.dxf.center.x, e.dxf.center.y), e.dxf.radius, layer=layer)
        if t == "ARC":
            return Arc((e.dxf.center.x, e.dxf.center.y), e.dxf.radius,
                       math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle), layer=layer)
        if t == "LWPOLYLINE":
            verts = [(p[0], p[1], p[4] if len(p) > 4 else 0.0) for p in e.get_points()]
            return LWPolyline(verts, closed=e.closed, layer=layer)
        if t == "POLYLINE":
            return _polyline_from_dxf(e, layer)
        if t == "ELLIPSE":
            return _ellipse_to_lwpolyline(e, layer)
        if t == "SPLINE":
            return _spline_to_lwpolyline(e, layer)
        if t == "TEXT":
            return TextEntity((e.dxf.insert.x, e.dxf.insert.y), e.dxf.height, e.dxf.text,
                              rotation=e.dxf.rotation, layer=layer)
        if t == "MTEXT":
            return _mtext_from_dxf(e, layer)
        if t == "POINT":
            return Point((e.dxf.location.x, e.dxf.location.y), layer=layer)
        if t == "SOLID" or t == "TRACE" or t == "3DFACE":
            return _solid_from_dxf(e, layer)
        if t == "HATCH":
            return _hatch_from_dxf(e, layer)
        if t == "DIMENSION":
            ent = _dim_from_dxf(e, subclass, layer)
            if ent is None:
                ent = _fallback_primitives(e, subclass, layer)
            return ent
        if t in ("LEADER", "MULTILEADER", "MLEADER"):
            ent = _leader_from_dxf(e, layer)
            if ent is None:
                ent = _fallback_primitives(e, subclass, layer)
            return ent
    except Exception:
        return None
    return None


def _polyline_from_dxf(e, layer):
    """Heavy POLYLINE (and 3D polyline): gather vertices + bulges. z dropped."""
    verts = []
    for v in e.vertices:
        loc = v.dxf.location
        bulge = getattr(v.dxf, "bulge", 0.0) or 0.0
        verts.append((float(loc.x), float(loc.y), float(bulge)))
    if not verts:
        return None
    return LWPolyline(verts, closed=e.closed, layer=layer)


def _ellipse_to_lwpolyline(e, layer):
    """Ellipses aren't a native 2D CAM primitive here, so approximate to a
    closed polyline (G-code / trim compatible)."""
    pts = [(p.x, p.y) for p in e.flattening(0.1)]
    if not pts:
        return None
    return LWPolyline([(x, y, 0.0) for x, y in pts], closed=True, layer=layer)


def _spline_to_lwpolyline(e, layer):
    pts = [(p.x, p.y) for p in e.flattening(0.1)]
    if not pts:
        return None
    return LWPolyline([(x, y, 0.0) for x, y in pts], closed=False, layer=layer)


def _mtext_from_dxf(e, layer):
    d = e.dxf
    insert = getattr(d, "insert", None)
    if insert is None:
        return None
    height = getattr(d, "char_height", 0.0) or getattr(d, "height", 0.0) or 2.5
    rotation = getattr(d, "rotation", 0.0) or 0.0
    text = e.text or ""
    return TextEntity((float(insert.x), float(insert.y)), float(height), text,
                      rotation=math.radians(rotation), layer=layer)


def _solid_from_dxf(e, layer):
    corners = []
    for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
        v = getattr(e.dxf, attr, None)
        if v is not None:
            corners.append((float(v.x), float(v.y)))
    if len(corners) < 3:
        return None
    return LWPolyline([(x, y, 0.0) for x, y in corners], closed=True, layer=layer)


def _hatch_from_dxf(e, layer):
    """Best-effort: pull the first closed boundary loop into our Hatch."""
    ptype_name = lambda p: str(getattr(getattr(p, "type", None), "name", getattr(p, "type", ""))).upper()
    for path in e.paths:
        pts = []
        if "POLYLINE" in ptype_name(path) or hasattr(path, "vertices"):
            for vx in path.vertices:
                pts.append((float(vx[0]), float(vx[1])))
        else:
            for edge in getattr(path, "edges", []) or []:
                pts.extend(_edge_points(edge))
        if len(pts) >= 3:
            return Hatch([(x, y) for x, y in pts], pattern="SOLID", layer=layer)
    return None


def _edge_points(edge):
    """Sample one HATCH edge path into (x, y) points."""
    et = getattr(edge, "EDGE_TYPE", "")
    if et == "LineEdge":
        return [(edge.start.x, edge.start.y), (edge.end.x, edge.end.y)]
    if et == "ArcEdge":
        cx, cy = edge.center.x, edge.center.y
        a0, a1 = edge.start_angle, edge.end_angle
        if a1 < a0:
            a1 += 2 * math.pi
        n = max(6, int((a1 - a0) / (math.pi / 24)))
        return [(cx + edge.radius * math.cos(a0 + (a1 - a0) * i / n),
                 cy + edge.radius * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    # EllipseEdge / SplineEdge / fallback: just keep the endpoints
    for attr in ("start", "end"):
        p = getattr(edge, attr, None)
        if p is not None:
            return [(float(p.x), float(p.y))]
    return []


def _fallback_primitives(e, subclass, layer):
    """When a DIMENSION/LEADER can't be rebuilt associatively, explode it to
    its raw graphic primitives (lines/arcs/text) so it is still visible."""
    try:
        out = []
        for pe in e.virtual_entities():
            ent = _from_dxf_entity(pe, subclass)
            if ent is not None:
                out.append(ent)
        return out[0] if len(out) == 1 else (out if out else None)
    except Exception:
        return None


def _dim_from_dxf(e, subclass, layer):
    d = e.dxf

    def P(attr, default=(0.0, 0.0)):
        v = getattr(d, attr, None)
        if v is None:
            return default
        return (float(v.x), float(v.y))

    p10 = P("defpoint")
    p13 = P("defpoint2")
    p14 = P("defpoint3")
    p15 = P("defpoint4")
    p16 = P("defpoint5")
    nz = lambda p: (p[0] != 0.0 or p[1] != 0.0)

    try:
        if subclass in ("AcDbAlignedDimension", "AcDbRotatedDimension", "AcDbLinearDimension"):
            ln = Line(p13, p14, layer=layer)
            loc = p16 if nz(p16) else p10
            return build_linear_dim(p13, p14, loc, layer, sources=[ln])
        if subclass in ("AcDbRadialDimension", "AcDbDiametricDimension"):
            diameter = (subclass == "AcDbDiametricDimension")
            oc = p15 if nz(p15) else p16
            if not nz(oc):
                return None
            r = max(math.hypot(oc[0] - p10[0], oc[1] - p10[1]), 1e-6)
            circ = Circle(p10, r, layer=layer)
            return build_radius_dim(p10, oc, layer, diameter=diameter, sources=[circ])
        if subclass in ("AcDb2LineAngularDimension", "AcDb3PointAngularDimension"):
            def collin(a, b, c):
                return abs((b[0] - a[0]) * (c[1] - a[1]) -
                           (b[1] - a[1]) * (c[0] - a[0])) < 1e-6
            if collin(p13, p14, p15):
                l1 = Line(p13, p14, layer=layer)
                l2 = Line(p15, p10, layer=layer)
                loc = p16 if nz(p16) else (0.0, 0.0)
            else:
                l1 = Line(p15, p13, layer=layer)
                l2 = Line(p15, p14, layer=layer)
                loc = p16 if nz(p16) else p10
            return build_angular_dim(l1, l2, loc, layer, sources=[l1, l2])
    except Exception:
        return None
    return None


def _leader_from_dxf(e, layer):
    verts = getattr(e.dxf, "vertices", None) or []
    pts = [(float(v.x), float(v.y)) for v in verts]
    if len(pts) < 2:
        return None
    text = getattr(e.dxf, "text", "") or ""
    return build_leader(pts, text, layer)


# --------------------------------------------------------------------------- save
def save_drawing(drawing, path):
    ext = os.path.splitext(path)[1].lower()
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    for name, props in drawing.layers.items():
        if name != "0" and name not in doc.layers:
            doc.layers.add(name, color=props.get("color", 7))
    for e in drawing.entities:
        _to_dxf_entity(msp, e)

    if ext == ".dxf":
        doc.saveas(path)
    elif ext == ".dwg":
        tmp_dxf = tempfile.mktemp(suffix=".dxf")
        doc.saveas(tmp_dxf)
        dxf_to_dwg(tmp_dxf, path)
    else:
        raise ValueError(f"Unsupported save extension: {ext}")
    drawing.filepath = path


def _to_dxf_entity(msp, ent):
    import math
    attribs = {"layer": ent.layer}
    if ent.kind == "LINE":
        msp.add_line(ent.p1, ent.p2, dxfattribs=attribs)
    elif ent.kind == "CIRCLE":
        msp.add_circle(ent.center, ent.radius, dxfattribs=attribs)
    elif ent.kind == "ARC":
        msp.add_arc(ent.center, ent.radius, math.degrees(ent.start_ang),
                    math.degrees(ent.end_ang), dxfattribs=attribs)
    elif ent.kind == "LWPOLYLINE":
        pts = [(v[0], v[1], 0, 0, v[2]) for v in ent.verts]
        msp.add_lwpolyline(pts, format="xyseb", close=ent.closed, dxfattribs=attribs)
    elif ent.kind == "ELLIPSE":
        maj = (ent.rx * math.cos(ent.rotation), ent.rx * math.sin(ent.rotation))
        ratio = (ent.ry / ent.rx) if ent.rx > 1e-9 else 1.0
        msp.add_ellipse(ent.center, major_axis=maj, ratio=ratio, dxfattribs=attribs)
    elif ent.kind == "POINT":
        msp.add_point(ent.pos, dxfattribs=attribs)
    elif ent.kind == "SOLID":
        msp.add_solid([(p[0], p[1]) for p in ent.points], dxfattribs=attribs)
    elif ent.kind == "HATCH":
        pts = [(p[0], p[1]) for p in ent.boundary]
        hatch = msp.add_hatch(dxfattribs=attribs)
        hatch.paths.add_polyline_path(pts, flags=1)
    elif ent.kind == "TEXT":
        msp.add_text(ent.text, dxfattribs={**attribs, "height": ent.height,
                                            "rotation": math.degrees(ent.rotation),
                                            "insert": ent.pos})
    elif ent.kind == "DIMENSION":
        _to_dxf_dimension(msp, ent, attribs)
    elif ent.kind == "LEADER":
        _to_dxf_leader(msp, ent, attribs)


def _export_dim_parts(msp, ent, attribs):
    """Fallback: write a dimension as plain geometry (lines/arcs/text) so it
    is always visible in any DXF viewer, matching the on-screen drawing."""
    for part in ent.parts:
        if part.kind == "LINE":
            msp.add_line(part.p1, part.p2, dxfattribs=attribs)
        elif part.kind == "ARC":
            msp.add_arc(part.center, part.radius, math.degrees(part.start_ang),
                        math.degrees(part.end_ang), dxfattribs=attribs)
        elif part.kind == "TEXT":
            msp.add_text(part.text, dxfattribs={**attribs, "height": part.height,
                                                "rotation": math.degrees(part.rotation),
                                                "insert": part.pos})


def _to_dxf_dimension(msp, ent, attribs):
    d = ent.defn or {}
    text = "<>"
    try:
        if ent.subtype == "angular" and len(ent.sources) >= 2:
            l1, l2 = ent.sources[0], ent.sources[1]
            loc = d.get("loc")
            if loc is None:
                raise ValueError("no loc")
            dim = msp.add_angular_dim_2l(
                base=loc,
                line1=(l1.p1, l1.p2),
                line2=(l2.p1, l2.p2),
                text=text,
                dimstyle="Standard",
                dxfattribs=attribs,
            )
            dim.render()
        elif ent.subtype in ("linear", "aligned", "rotated"):
            p1 = d.get("p1"); p2 = d.get("p2")
            dim_line = d.get("dim_line") or d.get("loc")
            if not (p1 and p2 and dim_line):
                raise ValueError("missing linear defn")
            ux = p2[0] - p1[0]; uy = p2[1] - p1[1]
            ln = math.hypot(ux, uy)
            if ln < 1e-9:
                raise ValueError("degenerate")
            nx, ny = -uy / ln, ux / ln
            dist = (dim_line[0] - p1[0]) * nx + (dim_line[1] - p1[1]) * ny
            dim = msp.add_aligned_dim(p1=p1, p2=p2, distance=dist,
                                      text=text, dimstyle="Standard",
                                      dxfattribs=attribs)
            dim.render()
        elif ent.subtype in ("radius", "radial"):
            c = d.get("center"); r = d.get("r"); ang = d.get("ang", 0.0)
            if c is None or r is None:
                raise ValueError("missing radial defn")
            dim = msp.add_radius_dim(center=c, radius=r, angle=math.degrees(ang),
                                     text=text, dimstyle="Standard",
                                     dxfattribs=attribs)
            dim.render()
        elif ent.subtype == "diameter":
            c = d.get("center"); r = d.get("r"); ang = d.get("ang", 0.0)
            if c is None or r is None:
                raise ValueError("missing diameter defn")
            dim = msp.add_diameter_dim(center=c, radius=r, angle=math.degrees(ang),
                                       text=text, dimstyle="Standard",
                                       dxfattribs=attribs)
            dim.render()
        else:
            raise ValueError("unknown dim subtype")
    except Exception:
        _export_dim_parts(msp, ent, attribs)


def _to_dxf_leader(msp, ent, attribs):
    pts = getattr(ent, "points", None)
    if pts and len(pts) >= 2:
        xy = [(p[0], p[1]) for p in pts]
        msp.add_lwpolyline(xy, dxfattribs=attribs)
    else:
        _export_dim_parts(msp, ent, attribs)
