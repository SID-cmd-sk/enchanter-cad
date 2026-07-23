"""
canvas.py
QPainter-based CAD canvas: world<->screen transform, pan/zoom, grid,
entity rendering, click-to-feed-points into the active command generator,
rubber-band selection.
"""
import math
from PyQt6.QtWidgets import QWidget, QInputDialog
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QCursor, QBrush, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal

from entities import (Line, Circle, Arc, LWPolyline, TextEntity, Point, Dimension,
                     Leader, Ellipse, Hatch, Solid)
from commands import Prompt, CommandContext, COMMANDS

GRID_COLOR = QColor(45, 45, 48)
AXIS_COLOR = QColor(80, 80, 85)
BG_COLOR = QColor(28, 28, 30)
ENTITY_COLOR = QColor(220, 220, 220)
SEL_COLOR = QColor(255, 165, 0)
CROSSHAIR_COLOR = QColor(120, 200, 255)


class Canvas(QWidget):
    status_message = pyqtSignal(str)
    coords_changed = pyqtSignal(float, float)
    command_finished = pyqtSignal(str)
    prompt_changed = pyqtSignal(str, str)  # (message, kind)

    def __init__(self, drawing, parent=None):
        super().__init__(parent)
        self.drawing = drawing
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.scale = 4.0          # pixels per drawing unit (mm)
        self.offset = QPointF(0, 0)  # world origin screen position
        self._panning = False
        self._pan_start = None
        self._rubber_start = None
        self._rubber_current = None

        self.active_cmd_name = None
        self.active_gen = None
        self.active_ctx = None
        self._pending_kind = None
        self._collected_points = []
        self._grip_drag = None
        self._grips = []
        self._cursor = (0.0, 0.0)

        self.ortho = False
        self.snap_enabled = True
        self.snap_modes = {"END", "MID", "CEN", "QUA", "INT"}
        self.grid_step = 10.0
        self._snap_marker = None   # world point currently snapped to

        self.fit_view()

    # ---------------------------------------------------------- transforms

    def world_to_screen(self, x, y):
        return QPointF(self.offset.x() + x * self.scale,
                        self.offset.y() - y * self.scale)

    def screen_to_world(self, sx, sy):
        return ((sx - self.offset.x()) / self.scale,
                 -(sy - self.offset.y()) / self.scale)

    def fit_view(self):
        x1, y1, x2, y2 = self.drawing.bbox()
        w, h = max(x2 - x1, 1e-3), max(y2 - y1, 1e-3)
        vw, vh = max(self.width(), 100), max(self.height(), 100)
        margin = 0.9
        self.scale = margin * min(vw / w, vh / h)
        self.scale = max(0.01, min(self.scale, 5000))
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        self.offset = QPointF(vw / 2.0 - cx * self.scale, vh / 2.0 + cy * self.scale)
        self.update()

    def zoom_window(self, p1, p2):
        x1, y1 = p1
        x2, y2 = p2
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        if w < 1e-6 or h < 1e-6:
            self.status_message.emit("Zoom window too small.")
            return
        vw, vh = max(self.width(), 100), max(self.height(), 100)
        self.scale = max(0.001, min(0.9 * min(vw / w, vh / h), 20000))
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        self.offset = QPointF(vw / 2.0 - cx * self.scale, vh / 2.0 + cy * self.scale)
        self.update()

    def plot_to_png(self, path):
        from PyQt6.QtGui import QPixmap
        pix = QPixmap(self.size())
        pix.fill(Qt.white)
        self.render(pix)
        pix.save(path)
        self.status_message.emit(f"Plotted to {path}")

    # ---------------------------------------------------------- command driving

    def start_command(self, name, gen_func):
        self.active_cmd_name = name
        self.active_ctx = CommandContext(self.drawing, self)
        self.active_gen = gen_func(self.active_ctx)
        self._collected_points = []
        self._sel_auto = False
        self._had_presel = bool(self.drawing.selected())
        self._advance(None)

    def _advance(self, value):
        try:
            prompt = self.active_gen.send(value)
        except StopIteration:
            self._end_command("Command complete.")
            return
        except Exception as e:
            import testlog
            testlog.log_error(self.active_cmd_name, e)
            self.status_message.emit(f"Error: {e}")
            self._end_command(f"Command failed: {e}")
            return
        if prompt.kind == Prompt.DONE:
            self._end_command(prompt.message)
            return
        if self._pending_kind == Prompt.POINT and isinstance(value, tuple) and len(value) == 2:
            self._collected_points.append((float(value[0]), float(value[1])))
        self._pending_kind = prompt.kind
        self.prompt_changed.emit(prompt.message, prompt.kind)
        if prompt.kind == Prompt.SELECTION and not self._sel_auto:
            if self._had_presel:
                sel = self.drawing.selected()
                if sel and self.active_gen is not None:
                    self._sel_auto = True
                    self._advance(sel)
            else:
                self._sel_auto = True
        self.update()

    def _end_command(self, message):
        if self.active_ctx and self.active_ctx.canvas_action == "zoom_extents":
            self.fit_view()
        self.active_cmd_name = None
        self.active_gen = None
        self.active_ctx = None
        self._pending_kind = None
        self._collected_points = []
        self.drawing.clear_selection()
        self.command_finished.emit(message)
        self.update()

    def cancel_command(self):
        if self.active_gen:
            self.active_gen.close()
        self.active_cmd_name = None
        self.active_gen = None
        self.active_ctx = None
        self._pending_kind = None
        self._collected_points = []
        self.command_finished.emit("*Cancel*")
        self.update()

    def feed_text(self, text):
        """Called from the command line widget when user types Enter."""
        if self.active_gen and self._pending_kind == Prompt.TEXT:
            self._advance(text if text != "" else None)
        elif self.active_gen and self._pending_kind == Prompt.POINT and text == "":
            self._advance(None)
        elif self.active_gen and self._pending_kind == Prompt.POINT and text != "":
            pt = self._parse_point_text(text)
            if pt is not None:
                self._advance(pt)
            else:
                self.status_message.emit("Invalid point - use X,Y or D<A (e.g. 100,50 or 75<30)")
        elif self.active_gen and self._pending_kind == Prompt.SELECTION and text == "":
            self._advance(self.drawing.selected())

    def _parse_point_text(self, text):
        """Parse typed point input for a POINT prompt.
        Supports:  X,Y (absolute) | @X,Y (relative) |
                   D<A (polar, angle in degrees) | @D<A (relative polar).
        Returns (x, y) or None if it can't be parsed.
        """
        t = text.strip()
        rel = t.startswith("@")
        if rel:
            t = t[1:]
        last = self._collected_points[-1] if self._collected_points else None
        try:
            if "<" in t:
                dpart, apart = t.split("<", 1)
                d = float(dpart)
                ang = math.radians(float(apart))
                dx, dy = d * math.cos(ang), d * math.sin(ang)
            elif "," in t:
                xs, ys = t.split(",", 1)
                px, py = float(xs), float(ys)
                if rel:
                    dx, dy = px, py
                else:
                    return (px, py)
            else:
                d = float(t)
                dx, dy = d, 0.0
            if last is not None:
                return (last[0] + dx, last[1] + dy)
            return (dx, dy)
        except ValueError:
            return None

    # ---------------------------------------------------------- object snaps

    def _snap_point(self, wx, wy):
        """Return the snapped world point for (wx, wy), or (wx, wy) unchanged
        if no enabled snap is within tolerance."""
        self._snap_marker = None
        if not self.snap_enabled:
            return (wx, wy)
        tol = 12.0 / self.scale
        cands = []  # (x, y, mode)
        for e in self.drawing.entities:
            if e.kind == "LINE":
                cands.append((e.p1[0], e.p1[1], "END"))
                cands.append((e.p2[0], e.p2[1], "END"))
                cands.append(((e.p1[0] + e.p2[0]) / 2, (e.p1[1] + e.p2[1]) / 2, "MID"))
            elif e.kind == "LWPOLYLINE":
                verts = e.verts
                n = len(verts)
                rng = range(n) if e.closed else range(n - 1)
                for i in rng:
                    x1, y1, _ = verts[i]
                    x2, y2, _ = verts[(i + 1) % n]
                    cands.append((x1, y1, "END"))
                    cands.append(((x1 + x2) / 2, (y1 + y2) / 2, "MID"))
            elif e.kind == "CIRCLE":
                cx, cy = e.center
                cands.append((cx, cy, "CEN"))
                for k in range(4):
                    a = math.pi / 2 * k
                    cands.append((cx + e.radius * math.cos(a), cy + e.radius * math.sin(a), "QUA"))
            elif e.kind == "ARC":
                cx, cy = e.center
                cands.append((cx, cy, "CEN"))
                pts = e.to_polyline_points(seg_len=max(0.2, e.radius / 30))
                cands.append((pts[0][0], pts[0][1], "END"))
                cands.append((pts[-1][0], pts[-1][1], "END"))
                cands.append(((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2, "MID"))
            elif e.kind == "POINT":
                cands.append((e.pos[0], e.pos[1], "END"))

        # intersections of LINE pairs (only when INT requested)
        if "INT" in self.snap_modes:
            lines = [e for e in self.drawing.entities if e.kind == "LINE"]
            for i in range(len(lines)):
                for j in range(i + 1, len(lines)):
                    ip = _seg_intersect(lines[i].p1, lines[i].p2, lines[j].p1, lines[j].p2)
                    if ip:
                        cands.append((ip[0], ip[1], "INT"))

        best, bestd, bestmode = None, tol, None
        for (x, y, mode) in cands:
            if mode not in self.snap_modes:
                continue
            d = math.hypot(x - wx, y - wy)
            if d < bestd:
                bestd, best, bestmode = d, (x, y), mode
        if best is not None:
            self._snap_marker = (best[0], best[1], bestmode)
            return best
        # NEArest: fall back to nearest point on any entity
        if "NEA" in self.snap_modes:
            near = None
            neard = tol
            for e in self.drawing.entities:
                pts = e.to_polyline_points(seg_len=max(0.1, 4.0 / self.scale))
                for i in range(len(pts) - 1):
                    proj = _proj_on_seg((wx, wy), pts[i], pts[i + 1])
                    d = math.hypot(proj[0] - wx, proj[1] - wy)
                    if d < neard:
                        neard, near = d, proj
            if near is not None:
                self._snap_marker = (near[0], near[1], "NEA")
                return near
        return (wx, wy)

    # ---------------------------------------------------------- painting

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), BG_COLOR)
        self._draw_grid(p)
        self._draw_entities(p)
        self._draw_grips(p)
        self._draw_preview(p)
        self._draw_rubber_band(p)
        p.end()

    def _draw_grid(self, p):
        step = self.grid_step
        while step * self.scale < 15:
            step *= 5
        while step * self.scale > 150:
            step /= 5
        x1, y1 = self.screen_to_world(0, self.height())
        x2, y2 = self.screen_to_world(self.width(), 0)
        p.setPen(QPen(GRID_COLOR, 1))
        gx = math.floor(x1 / step) * step
        while gx <= x2:
            sp = self.world_to_screen(gx, 0)
            p.drawLine(int(sp.x()), 0, int(sp.x()), self.height())
            gx += step
        gy = math.floor(y1 / step) * step
        while gy <= y2:
            sp = self.world_to_screen(0, gy)
            p.drawLine(0, int(sp.y()), self.width(), int(sp.y()))
            gy += step
        p.setPen(QPen(AXIS_COLOR, 2))
        origin = self.world_to_screen(0, 0)
        p.drawLine(0, int(origin.y()), self.width(), int(origin.y()))
        p.drawLine(int(origin.x()), 0, int(origin.x()), self.height())

    def _draw_entities(self, p):
        for e in self.drawing.entities:
            if e.kind in ("DIMENSION", "LEADER"):
                e.recompute()   # keep associative dims tied to their source entities
                pen = QPen(SEL_COLOR if e.selected else QColor(120, 200, 255), 1.2)
                p.setPen(pen)
                for part in e.parts:
                    self._draw_one(p, part)
                continue
            pen = QPen(SEL_COLOR if e.selected else ENTITY_COLOR, 1.4)
            p.setPen(pen)
            self._draw_one(p, e)

    def _draw_one(self, p, e):
        if e.kind == "LINE":
            a, b = self.world_to_screen(*e.p1), self.world_to_screen(*e.p2)
            p.drawLine(a, b)
        elif e.kind == "CIRCLE":
            c = self.world_to_screen(*e.center)
            r = e.radius * self.scale
            p.drawEllipse(c, r, r)
        elif e.kind == "ARC":
            pts = e.to_polyline_points(seg_len=max(0.2, e.radius / 30))
            self._draw_polyline(p, pts)
        elif e.kind == "LWPOLYLINE":
            pts = e.to_polyline_points(seg_len=1.0)
            self._draw_polyline(p, pts)
        elif e.kind == "TEXT":
            pos = self.world_to_screen(*e.pos)
            f = QFont("Consolas", max(6, int(e.height * self.scale)))
            p.setFont(f)
            p.drawText(pos, e.text)
        elif e.kind == "POINT":
            cx, cy = self.world_to_screen(*e.pos)
            s = max(3, int(e.size * self.scale))
            p.drawLine(int(cx - s), int(cy), int(cx + s), int(cy))
            p.drawLine(int(cx), int(cy - s), int(cx), int(cy + s))
        elif e.kind == "ELLIPSE":
            self._draw_polygon_fill(p, e.to_polyline_points(), e.selected)
        elif e.kind == "HATCH":
            self._draw_polygon_fill(p, e.boundary, e.selected)
        elif e.kind == "SOLID":
            self._draw_polygon_fill(p, e.points, e.selected)

    def _draw_polygon_fill(self, p, pts, selected):
        if len(pts) < 3:
            self._draw_polyline(p, pts)
            return
        poly = QPolygonF([self.world_to_screen(*pt) for pt in pts])
        fill = SEL_COLOR if selected else QColor(170, 170, 170)
        p.setBrush(QBrush(fill))
        p.setPen(QPen(ENTITY_COLOR, 0.5))
        p.drawPolygon(poly)
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_polyline(self, p, pts):
        for i in range(len(pts) - 1):
            a = self.world_to_screen(*pts[i])
            b = self.world_to_screen(*pts[i + 1])
            p.drawLine(a, b)

    def _draw_preview(self, p):
        """Live rubber-band / ghost preview that follows the cursor while a
        command is active (DraftSight/SolidWorks-style), for every command."""
        if not self.active_gen or self._pending_kind is None:
            return
        cur = self._cursor
        name = self.active_cmd_name
        sel = self.drawing.selected()
        dash = QPen(CROSSHAIR_COLOR, 1, Qt.PenStyle.DashLine)

        # ---- Transform / modify: ghost of the selection following the cursor ----
        if sel and self._collected_points:
            base = self._collected_points[0]
            if name in ("MOVE", "COPY") and self._pending_kind == Prompt.POINT:
                dx, dy = cur[0] - base[0], cur[1] - base[1]
                ghosts = [e.clone() for e in sel]
                for g in ghosts:
                    g.translate(dx, dy)
                self._render_preview_entities(p, ghosts)
                return
            if name == "ROTATE" and self._pending_kind in (Prompt.POINT, Prompt.TEXT):
                ang = math.atan2(cur[1] - base[1], cur[0] - base[0])
                ghosts = [e.clone() for e in sel]
                for g in ghosts:
                    g.rotate(base[0], base[1], ang)
                self._render_preview_entities(p, ghosts)
                return
            if name == "MIRROR" and len(self._collected_points) == 1 and self._pending_kind == Prompt.POINT:
                ghosts = [e.clone() for e in sel]
                for g in ghosts:
                    g.mirror(base, cur)
                self._render_preview_entities(p, ghosts)
                return
            if name == "SCALE" and self._pending_kind in (Prompt.POINT, Prompt.TEXT):
                cx, cy = self._selection_centroid(sel)
                ref = math.hypot(cx - base[0], cy - base[1])
                d = math.hypot(cur[0] - base[0], cur[1] - base[1])
                f = d / ref if ref > 1e-9 else 1.0
                ghosts = [e.clone() for e in sel]
                for g in ghosts:
                    g.scale(base[0], base[1], f)
                self._render_preview_entities(p, ghosts)
                return

        # ---- CIRCLE: preview radius from center to cursor ----
        if name == "CIRCLE" and len(self._collected_points) == 1 and self._pending_kind == Prompt.POINT:
            c = self._collected_points[0]
            r = math.hypot(cur[0] - c[0], cur[1] - c[1])
            if r > 1e-6:
                sc = self.world_to_screen(*c)
                p.setPen(dash)
                p.drawEllipse(sc, r * self.scale, r * self.scale)
                a = sc
                b = self.world_to_screen(*cur)
                p.drawLine(a, b)
            return

        # ---- RECTANG: preview rectangle from first corner to cursor ----
        if name == "RECTANG" and len(self._collected_points) == 1 and self._pending_kind == Prompt.POINT:
            a = self.world_to_screen(*self._collected_points[0])
            b = self.world_to_screen(*cur)
            p.setPen(dash)
            p.drawRect(QRectF(a, b).normalized())
            return

        # ---- ARC: 3-point preview ----
        if name == "ARC" and len(self._collected_points) >= 1 and self._pending_kind == Prompt.POINT:
            if len(self._collected_points) == 1:
                a = self.world_to_screen(*self._collected_points[0])
                b = self.world_to_screen(*cur)
                p.setPen(dash)
                p.drawLine(a, b)
            else:
                arc = self._arc_through_3(self._collected_points[0],
                                          self._collected_points[1], cur)
                if arc:
                    self._render_preview_entities(p, [arc])
            return

        # ---- POLYGON: rough radius circle about the center ----
        if name == "POLYGON" and len(self._collected_points) == 1 and self._pending_kind == Prompt.POINT:
            c = self._collected_points[0]
            r = math.hypot(cur[0] - c[0], cur[1] - c[1])
            if r > 1e-6:
                p.setPen(dash)
                p.drawEllipse(self.world_to_screen(*c), r * self.scale, r * self.scale)
            return

        # ---- Generic: rubber line from the last placed point to the cursor ----
        if self._pending_kind == Prompt.POINT and self._collected_points:
            last = self._collected_points[-1]
            a = self.world_to_screen(*last)
            b = self.world_to_screen(*cur)
            p.setPen(dash)
            p.drawLine(a, b)
            p.setPen(QPen(CROSSHAIR_COLOR, 2))
            p.drawEllipse(b, 3, 3)

        # ---- snap marker (square box at the snapped point) ----
        if self._snap_marker and (self._pending_kind == Prompt.POINT or
                                   (self.active_gen is None and self._snap_marker)):
            sx, sy, mode = self._snap_marker
            sp = self.world_to_screen(sx, sy)
            p.setPen(QPen(QColor(255, 230, 0), 1.5))
            s = 5
            p.drawRect(int(sp.x()) - s, int(sp.y()) - s, 2 * s, 2 * s)

    def _render_preview_entities(self, p, ents):
        pen = QPen(CROSSHAIR_COLOR, 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        for e in ents:
            if e.kind in ("DIMENSION", "LEADER"):
                for part in e.parts:
                    self._draw_one(p, part)
                continue
            self._draw_one(p, e)

    def _selection_centroid(self, sel):
        pts = []
        for e in sel:
            pts.extend(e.to_polyline_points(seg_len=2.0))
        if not pts:
            return (0.0, 0.0)
        n = len(pts)
        return (sum(x for x, y in pts) / n, sum(y for x, y in pts) / n)

    def _arc_through_3(self, p1, p2, p3):
        ax, ay = p1; bx, by = p2; cx, cy = p3
        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(d) < 1e-9:
            return None
        ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) +
              (cx**2 + cy**2) * (ay - by)) / d
        uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) +
              (cx**2 + cy**2) * (bx - ax)) / d
        r = math.hypot(ax - ux, ay - uy)
        a1 = math.atan2(ay - uy, ax - ux)
        a3 = math.atan2(cy - uy, cx - ux)
        a2 = math.atan2(by - uy, bx - ux)

        def between(a, s, e):
            while e < s:
                e += 2 * math.pi
            while a < s:
                a += 2 * math.pi
            return s <= a <= e

        sa, ea = a1, a3
        if not between(a2, sa, ea):
            sa, ea = ea, sa
            if not between(a2, sa, ea):
                sa, ea = a1, a3
        return Arc((ux, uy), r, sa, ea)

    def _confirm_scalar_from_cursor(self, wx, wy):
        """Let ROTATE/SCALE be confirmed by clicking (the preview already
        follows the cursor): rotation angle or scale factor from the cursor
        position, matching the live ghost preview."""
        if not self._collected_points:
            return
        base = self._collected_points[0]
        name = self.active_cmd_name
        if name == "ROTATE":
            ang = math.degrees(math.atan2(wy - base[1], wx - base[0]))
            self.feed_text(f"{ang:.4f}")
        elif name == "SCALE":
            sel = self.drawing.selected()
            if not sel:
                return
            cx, cy = self._selection_centroid(sel)
            ref = math.hypot(cx - base[0], cy - base[1])
            d = math.hypot(wx - base[0], wy - base[1])
            f = d / ref if ref > 1e-9 else 1.0
            self.feed_text(f"{f:.4f}")

    def _draw_rubber_band(self, p):
        if self._rubber_start and self._rubber_current:
            rect = QRectF(self._rubber_start, self._rubber_current).normalized()
            crossing = self._rubber_current.x() < self._rubber_start.x()
            pen = QPen(QColor(0, 200, 0) if crossing else QColor(0, 120, 255), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(rect)

    # ---------------------------------------------------------- mouse/keys

    def mousePressEvent(self, ev):
        self.setFocus()
        wx, wy = self.screen_to_world(ev.position().x(), ev.position().y())
        if ev.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = ev.position()
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            if self.active_gen and self._pending_kind == Prompt.POINT:
                pt = self._snap_point(wx, wy)
                self._advance(pt)
                return
            if self.active_gen and self._pending_kind == Prompt.SELECTION:
                self._rubber_start = ev.position()
                self._rubber_current = ev.position()
                return
            if self.active_gen and self._pending_kind == Prompt.TEXT and \
                    self.active_cmd_name in ("ROTATE", "SCALE"):
                self._confirm_scalar_from_cursor(wx, wy)
                return
            if not self.active_gen:
                # grip drag takes priority (edit endpoints / relocate dims)
                g = self._grip_at(wx, wy)
                if g:
                    self.drawing.push_undo()
                    self._grip_drag = g
                    self._grip_ref = (wx, wy)
                    return
                # interactive select / start rubber band
                hit = self._hit_test(wx, wy)
                if hit and not (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self.drawing.clear_selection()
                if hit:
                    hit.selected = not hit.selected if (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier) else True
                    self.update()
                else:
                    self._rubber_start = ev.position()
                    self._rubber_current = ev.position()
        if ev.button() == Qt.MouseButton.RightButton:
            self.cancel_command()

    def mouseMoveEvent(self, ev):
        wx, wy = self.screen_to_world(ev.position().x(), ev.position().y())
        if self._grip_drag:
            self._apply_grip(self._grip_drag, wx, wy)
            self.update()
            return
        if self._panning or self._rubber_start:
            self._cursor = (wx, wy)
            self._snap_marker = None
        else:
            self._cursor = self._snap_point(wx, wy)
        self.coords_changed.emit(*self._cursor)
        if self._panning and self._pan_start:
            d = ev.position() - self._pan_start
            self.offset += d
            self._pan_start = ev.position()
            self.update()
            return
        if self._rubber_start:
            self._rubber_current = ev.position()
            self.update()
            return
        if self.active_gen or self.snap_enabled:
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            return
        if ev.button() == Qt.MouseButton.LeftButton and self._grip_drag:
            self._grip_drag = None
            self.update()
            return
        if ev.button() == Qt.MouseButton.LeftButton and self._rubber_start:
            rect = QRectF(self._rubber_start, self._rubber_current or self._rubber_start).normalized()
            shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            is_click = rect.width() < 3 and rect.height() < 3
            if self.active_gen and self._pending_kind == Prompt.SELECTION:
                if is_click:
                    wx, wy = self.screen_to_world(self._rubber_start.x(), self._rubber_start.y())
                    hit = self._hit_test(wx, wy)
                    if hit:
                        if shift:
                            hit.selected = not hit.selected
                        else:
                            self.drawing.clear_selection()
                            hit.selected = True
                        hits = self.drawing.selected()
                    else:
                        if not shift:
                            self.drawing.clear_selection()
                        hits = []
                else:
                    crossing = self._rubber_current.x() < self._rubber_start.x()
                    hits = self._box_select(rect, crossing)
                    for h in hits:
                        h.selected = True
                self._rubber_start = None
                self._rubber_current = None
                self._advance(hits)
                return
            if is_click:
                wx, wy = self.screen_to_world(self._rubber_start.x(), self._rubber_start.y())
                hit = self._hit_test(wx, wy)
                if hit:
                    if shift:
                        hit.selected = not hit.selected
                    else:
                        self.drawing.clear_selection()
                        hit.selected = True
                    self.update()
            else:
                crossing = self._rubber_current.x() < self._rubber_start.x()
                hits = self._box_select(rect, crossing)
                for h in hits:
                    h.selected = True
            self._rubber_start = None
            self._rubber_current = None
            self.update()

    def wheelEvent(self, ev):
        wx, wy = self.screen_to_world(ev.position().x(), ev.position().y())
        factor = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        self.scale *= factor
        self.scale = max(0.001, min(self.scale, 20000))
        new_screen = self.world_to_screen(wx, wy)
        self.offset += ev.position() - new_screen
        self.update()

    def mouseDoubleClickEvent(self, ev):
        if self.active_gen:
            return
        wx, wy = self.screen_to_world(ev.position().x(), ev.position().y())
        hit = self._hit_test(wx, wy)
        if hit and hit.kind == "DIMENSION":
            cur = hit.measurement
            txt, ok = QInputDialog.getText(self, "Edit Dimension",
                                           "New value:", text=f"{cur:.4f}")
            if ok and txt:
                try:
                    v = float(txt)
                    self.drawing.push_undo()
                    hit.apply_value(v)
                    self.update()
                except ValueError:
                    self.status_message.emit("Invalid number.")
            return
        if hit:
            self.drawing.clear_selection()
            hit.selected = True
            self.update()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.cancel_command()
        elif ev.key() == Qt.Key.Key_F8:
            self.ortho = not self.ortho
            self.status_message.emit(f"ORTHO {'ON' if self.ortho else 'OFF'}")
        elif ev.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.active_gen is None:
                sel = self.drawing.selected()
                if sel:
                    self.drawing.push_undo()
                    for e in sel:
                        self.drawing.remove(e)
                    self.update()
                    self.status_message.emit(f"Erased {len(sel)} object(s).")
        elif ev.key() == Qt.Key.Key_F3:
            self.snap_enabled = not self.snap_enabled
            self.status_message.emit(f"OBJECT SNAP {'ON' if self.snap_enabled else 'OFF'}"
                                     f" ({' '.join(sorted(self.snap_modes)) or '-'})")
        else:
            super().keyPressEvent(ev)

    # ---------------------------------------------------------- hit testing

    # ---------------------------------------------------------- grips / direct edit
    def _compute_grips(self):
        grips = []
        for e in self.drawing.entities:
            if not e.selected:
                continue
            if e.kind == "LINE":
                grips.append({"ent": e, "ref": 0, "pt": e.p1})
                grips.append({"ent": e, "ref": 1, "pt": e.p2})
            elif e.kind == "CIRCLE":
                cx, cy = e.center
                grips.append({"ent": e, "ref": "center", "pt": (cx, cy)})
                grips.append({"ent": e, "ref": "radius", "pt": (cx + e.radius, cy)})
            elif e.kind == "ARC":
                cx, cy = e.center
                grips.append({"ent": e, "ref": "center", "pt": (cx, cy)})
                grips.append({"ent": e, "ref": "start",
                              "pt": (cx + e.radius * math.cos(e.start_ang),
                                     cy + e.radius * math.sin(e.start_ang))})
                grips.append({"ent": e, "ref": "end",
                              "pt": (cx + e.radius * math.cos(e.end_ang),
                                     cy + e.radius * math.sin(e.end_ang))})
            elif e.kind == "DIMENSION":
                grips.append({"ent": e, "ref": "loc", "pt": self._dim_loc_pt(e)})
        return grips

    def _dim_loc_pt(self, dim):
        t = dim.subtype
        if t == "linear":
            return dim.defn.get("loc") or (0.0, 0.0)
        if t == "radial" and dim.sources:
            c = dim.sources[0].center
            a = dim.defn.get("ang", 0.0)
            r = dim.sources[0].radius
            return (c[0] + r * math.cos(a), c[1] + r * math.sin(a))
        if t == "angular":
            return dim.defn.get("loc") or (0.0, 0.0)
        return (0.0, 0.0)

    def _grip_at(self, wx, wy):
        tol = 8.0 / self.scale
        best, bestd = None, tol
        for g in getattr(self, "_grips", []):
            d = math.hypot(g["pt"][0] - wx, g["pt"][1] - wy)
            if d < bestd:
                bestd, best = d, g
        return best

    def _set_dim_loc(self, dim, wx, wy):
        t = dim.subtype
        if t == "linear":
            dim.defn["loc"] = (wx, wy)
        elif t == "radial" and dim.sources:
            c = dim.sources[0].center
            dim.defn["ang"] = math.atan2(wy - c[1], wx - c[0])
        elif t == "angular":
            dim.defn["loc"] = (wx, wy)
        dim.recompute()

    def _apply_grip(self, g, wx, wy):
        e = g["ent"]
        if e.kind == "LINE":
            if g["ref"] == 0:
                e.p1 = (wx, wy)
            else:
                e.p2 = (wx, wy)
        elif e.kind == "CIRCLE":
            if g["ref"] == "center":
                dx, dy = wx - g["pt"][0], wy - g["pt"][1]
                e.center = (e.center[0] + dx, e.center[1] + dy)
                g["pt"] = (g["pt"][0] + dx, g["pt"][1] + dy)
            elif g["ref"] == "radius":
                e.radius = max(0.01, math.hypot(wx - e.center[0], wy - e.center[1]))
        elif e.kind == "ARC":
            if g["ref"] == "center":
                dx, dy = wx - g["pt"][0], wy - g["pt"][1]
                e.center = (e.center[0] + dx, e.center[1] + dy)
                g["pt"] = (g["pt"][0] + dx, g["pt"][1] + dy)
            elif g["ref"] in ("start", "end"):
                a = math.atan2(wy - e.center[1], wx - e.center[0])
                if g["ref"] == "start":
                    e.start_ang = a
                else:
                    e.end_ang = a
                sweep = e.end_ang - e.start_ang
                while sweep <= 0:
                    e.end_ang += 2 * math.pi
                    sweep += 2 * math.pi
        elif e.kind == "DIMENSION":
            self._set_dim_loc(e, wx, wy)

    def _draw_grips(self, p):
        self._grips = self._compute_grips()
        if not self._grips:
            return
        pen = QPen(QColor(255, 200, 0), 1)
        brush = QBrush(QColor(40, 40, 45))
        p.setPen(pen)
        p.setBrush(brush)
        s = max(4, int(5.0))
        for g in self._grips:
            sp = self.world_to_screen(*g["pt"])
            p.drawRect(int(sp.x() - s / 2), int(sp.y() - s / 2), s, s)

    def _hit_test(self, wx, wy):
        tol = 6.0 / self.scale
        best, bestd = None, tol
        for e in self.drawing.entities:
            d = self._dist_to_entity(e, wx, wy)
            if d is not None and d < bestd:
                bestd, best = d, e
        return best

    def _dist_to_entity(self, e, wx, wy):
        if e.kind in ("DIMENSION", "LEADER"):
            pts = []
            for part in e.parts:
                pts.extend(part.to_polyline_points(seg_len=max(0.1, 5.0 / self.scale)))
        else:
            pts = e.to_polyline_points(seg_len=max(0.1, 5.0 / self.scale))
        best = None
        for i in range(len(pts) - 1):
            d = _pt_seg_dist((wx, wy), pts[i], pts[i + 1])
            if best is None or d < best:
                best = d
        return best

    def _box_select(self, rect, crossing):
        x1, y1 = self.screen_to_world(rect.left(), rect.bottom())
        x2, y2 = self.screen_to_world(rect.right(), rect.top())
        lo_x, hi_x = min(x1, x2), max(x1, x2)
        lo_y, hi_y = min(y1, y2), max(y1, y2)
        hits = []
        for e in self.drawing.entities:
            bx1, by1, bx2, by2 = e.bbox()
            fully_inside = bx1 >= lo_x and bx2 <= hi_x and by1 >= lo_y and by2 <= hi_y
            intersects = not (bx2 < lo_x or bx1 > hi_x or by2 < lo_y or by1 > hi_y)
            if crossing and intersects:
                hits.append(e)
            elif not crossing and fully_inside:
                hits.append(e)
        return hits


def _pt_seg_dist(p, a, b):
    px, py = p; ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _proj_on_seg(p, a, b):
    px, py = p; ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return a
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return (ax + t * dx, ay + t * dy)


def _seg_intersect(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
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
