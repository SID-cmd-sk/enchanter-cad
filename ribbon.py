"""
ribbon.py
AutoCAD / DraftSight-style tabbed ribbon for PyCAD.

* Icons are generated in-code (no image files) by IconFactory, which draws
  simple vector glyphs for each command. Unknown commands fall back to a
  generic glyph with the command's first letter.
* Ribbon is organised into tabs (Draw / Modify / Annotate / View / Tools /
  File), each tab holding grouped command panels.
"""
from PyQt6.QtWidgets import (QTabWidget, QWidget, QHBoxLayout, QVBoxLayout,
                              QPushButton, QLabel, QComboBox, QFrame, QSizePolicy)
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QFont, QBrush
from PyQt6.QtCore import Qt, QSize, QRect


class IconFactory:
    """Draws small vector glyphs for command buttons."""

    SIZE = 32

    def __init__(self):
        self.cache = {}

    def _draw(self, name, size):
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = size
        m = max(3, int(s * 0.14))
        col = QColor(225, 230, 235)
        p.setPen(QPen(col, max(1.5, s * 0.045)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        fn = self._glyphs.get(name)
        if fn is None:
            fn = IconFactory._generic
        fn(self, p, s, m, name)
        p.end()
        return pm

    def icon(self, name, size=SIZE):
        key = (name, size)
        if key not in self.cache:
            self.cache[key] = QIcon(self._draw(name, size))
        return self.cache[key]

    # ---------------------------------------------------- glyph helpers
    def _generic(self, p, s, m, name):
        p.drawRect(m, m, s - 2 * m, s - 2 * m)
        p.setFont(QFont("Arial", int(s * 0.4), QFont.Weight.Bold))
        p.drawText(QRect(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, (name[:1] or "?").upper())

    def _line(self, p, s, m, n):
        p.drawLine(m, s - m, s - m, m)

    def _circle(self, p, s, m, n):
        p.drawEllipse(m, m, s - 2 * m, s - 2 * m)

    def _arc(self, p, s, m, n):
        p.drawArc(m, m, s - 2 * m, s - 2 * m, 30 * 16, 120 * 16)

    def _polyline(self, p, s, m, n):
        pts = [(m, s - m), (s - m, s - m), (s - m, m), (m, int(s * 0.4))]
        for i in range(len(pts) - 1):
            p.drawLine(*pts[i], *pts[i + 1])

    def _rect(self, p, s, m, n):
        p.drawRect(m, m, s - 2 * m, s - 2 * m)

    def _polygon(self, p, s, m, n):
        import math
        cx, cy = s / 2, s / 2
        r = (s - 2 * m) / 2
        pts = []
        for i in range(6):
            a = math.radians(60 + i * 60)
            pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            p.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))

    def _ellipse(self, p, s, m, n):
        p.drawEllipse(m, int(s * 0.3), s - 2 * m, int(s * 0.4))

    def _point(self, p, s, m, n):
        cx, cy = int(s / 2), int(s / 2)
        r = max(2, int(s * 0.07))
        p.setBrush(QColor(225, 230, 235))
        p.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)

    def _text(self, p, s, m, n):
        p.setFont(QFont("Arial", int(s * 0.45), QFont.Weight.Bold))
        p.drawText(QRect(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, "T")

    def _move(self, p, s, m, n):
        p.drawLine(m, s - m, s - m, m)
        p.drawLine(s - m, m, s - m - int(s * 0.2), m + int(s * 0.12))
        p.drawLine(s - m, m, s - m - int(s * 0.18), m + int(s * 0.05))

    def _copy(self, p, s, m, n):
        p.drawRect(m, m, s // 3, s // 3)
        p.drawRect(s - m - s // 3, s - m - s // 3, s // 3, s // 3)

    def _rotate(self, p, s, m, n):
        p.drawArc(m, m, s - 2 * m, s - 2 * m, 60 * 16, 270 * 16)
        p.drawLine(s - m - int(s * 0.18), int(s * 0.42), s - m, int(s * 0.3))
        p.drawLine(s - m, int(s * 0.3), s - m - int(s * 0.02), int(s * 0.5))

    def _scale(self, p, s, m, n):
        p.drawRect(m, m, s // 2 - m, s // 2 - m)
        p.drawRect(s // 2, s // 2, s // 2 - m, s // 2 - m)

    def _mirror(self, p, s, m, n):
        p.drawLine(int(s / 2), m, int(s / 2), s - m)
        p.drawLine(m, s - m, s - m, s - m)
        p.drawLine(m, m, s - m, s - m)

    def _offset(self, p, s, m, n):
        p.drawRect(m, m, s - 2 * m, s - 2 * m)
        p.drawRect(m + int(s * 0.18), m + int(s * 0.18), s - 2 * m - int(s * 0.36), s - 2 * m - int(s * 0.36))

    def _array(self, p, s, m, n):
        for i in range(3):
            for j in range(3):
                x = m + i * (s - 2 * m) // 2
                y = m + j * (s - 2 * m) // 2
                p.drawRect(x, y, (s - 2 * m) // 2 - 2, (s - 2 * m) // 2 - 2)

    def _trim(self, p, s, m, n):
        p.drawLine(m, int(s * 0.3), s - m, int(s * 0.3))
        p.drawLine(int(s * 0.6), m, int(s * 0.6), s - m)

    def _fillet(self, p, s, m, n):
        p.drawLine(m, s - m, s - m, s - m)
        p.drawLine(s - m, s - m, s - m, m)
        p.drawArc(s - m - int(s * 0.4), s - m - int(s * 0.4), int(s * 0.4), int(s * 0.4), 180 * 16, 90 * 16)

    def _chamfer(self, p, s, m, n):
        p.drawLine(m, s - m, s - m, s - m)
        p.drawLine(s - m, s - m, s - m, m)
        p.drawLine(int(s * 0.65), s - m, s - m, int(s * 0.65))

    def _erase(self, p, s, m, n):
        p.drawLine(int(s * 0.3), int(s * 0.3), int(s * 0.7), int(s * 0.7))
        p.drawLine(int(s * 0.7), int(s * 0.3), int(s * 0.3), int(s * 0.7))

    def _explode(self, p, s, m, n):
        p.drawRect(m, m, s - 2 * m, s - 2 * m)
        p.drawLine(m, int(s / 2), s - m, int(s / 2))
        p.drawLine(int(s / 2), m, int(s / 2), s - m)

    def _join(self, p, s, m, n):
        p.drawLine(m, int(s * 0.6), int(s * 0.45), int(s * 0.6))
        p.drawLine(int(s * 0.55), int(s * 0.4), s - m, int(s * 0.4))

    def _stretch(self, p, s, m, n):
        p.drawLine(m, s - m, s - m, s - m)
        p.drawLine(int(s * 0.6), m, int(s * 0.6), s - m)
        p.drawLine(int(s * 0.6), m, int(s * 0.35), m + int(s * 0.15))

    def _break(self, p, s, m, n):
        p.drawLine(m, int(s / 2), int(s * 0.4), int(s / 2))
        p.drawLine(int(s * 0.6), int(s / 2), s - m, int(s / 2))
        p.drawEllipse(int(s * 0.4), int(s / 2) - 2, int(s * 0.2), 4)

    def _zoom(self, p, s, m, n):
        self._circle(p, s, m, n)
        p.drawLine(int(s * 0.72), int(s * 0.72), s - m, s - m)

    def _pan(self, p, s, m, n):
        p.drawLine(int(s * 0.3), int(s / 2), int(s * 0.7), int(s / 2))
        p.drawLine(int(s * 0.3), int(s / 2), int(s * 0.45), int(s * 0.4))
        p.drawLine(int(s * 0.3), int(s / 2), int(s * 0.45), int(s * 0.6))

    def _gcode(self, p, s, m, n):
        import math
        cx, cy = s / 2, s / 2
        r = (s - 2 * m) / 2
        p.drawEllipse(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
        p.drawEllipse(int(cx - r * 0.45), int(cy - r * 0.45), int(r * 0.9), int(r * 0.9))
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(int(cx + r * math.cos(a)), int(cy + r * math.sin(a)),
                       int(cx + (r + m) * math.cos(a)), int(cy + (r + m) * math.sin(a)))

    def _new(self, p, s, m, n):
        p.drawRect(m, m, s - 2 * m, s - 2 * m)
        p.drawLine(m, m, s - m, s - m)
        p.drawLine(s - m, m, m, s - m)

    def _open(self, p, s, m, n):
        p.drawRect(m, int(s * 0.4), s - 2 * m, s - m - int(s * 0.4))
        p.drawLine(m, int(s * 0.4), int(s * 0.35), m)
        p.drawLine(int(s * 0.35), m, int(s * 0.55), m)
        p.drawLine(int(s * 0.55), m, s - m, int(s * 0.4))

    def _save(self, p, s, m, n):
        p.drawRect(m, m, s - 2 * m, s - 2 * m)
        p.drawRect(int(s * 0.35), m, int(s * 0.3), int(s * 0.3))
        p.drawLine(int(s * 0.3), int(s * 0.55), int(s * 0.7), int(s * 0.55))

    def _saveas(self, p, s, m, n):
        self._save(p, s, m, n)
        p.drawLine(int(s * 0.6), m, s - m, int(s * 0.4))

    def _plot(self, p, s, m, n):
        p.drawRect(m, int(s * 0.4), s - 2 * m, s - m - int(s * 0.4))
        p.drawLine(int(s * 0.3), int(s * 0.4), int(s * 0.3), m)
        p.drawLine(int(s * 0.7), int(s * 0.4), int(s * 0.7), m)
        p.drawLine(int(s * 0.3), m, int(s * 0.7), m)
        p.drawLine(int(s * 0.5), int(s * 0.6), int(s * 0.5), int(s * 0.85))

    def _hatch(self, p, s, m, n):
        self._rect(p, s, m, n)
        for i in range(1, 5):
            y = m + i * (s - 2 * m) // 5
            p.drawLine(m, y, s - m, y)

    def _dim(self, p, s, m, n):
        p.drawLine(m, int(s * 0.7), s - m, int(s * 0.7))
        p.drawLine(m, int(s * 0.6), m, int(s * 0.8))
        p.drawLine(s - m, int(s * 0.6), s - m, int(s * 0.8))
        p.drawLine(m, int(s * 0.5), s - m, int(s * 0.5))

    def _leader(self, p, s, m, n):
        p.drawLine(m, s - m, s - m, m)
        p.drawLine(s - m, m, s - m - int(s * 0.2), m + int(s * 0.15))

    def _regen(self, p, s, m, n):
        p.drawEllipse(int(s * 0.35), int(s * 0.35), int(s * 0.3), int(s * 0.3))
        p.drawLine(int(s * 0.5), int(s * 0.5), s - m, s - m)

    def _layer(self, p, s, m, n):
        p.drawRect(m, m, s - 2 * m, s - 2 * m)
        p.drawLine(m, int(s * 0.45), s - m, int(s * 0.45))
        p.drawLine(m, int(s * 0.7), s - m, int(s * 0.7))

    _glyphs = {
        "LINE": _line, "CIRCLE": _circle, "ARC": _arc, "PLINE": _polyline,
        "RECTANG": _rect, "POLYGON": _polygon, "ELLIPSE": _ellipse, "POINT": _point,
        "TEXT": _text, "MTEXT": _text, "MOVE": _move, "COPY": _copy, "ROTATE": _rotate,
        "SCALE": _scale, "MIRROR": _mirror, "OFFSET": _offset, "ARRAY": _array,
        "TRIM": _trim, "FILLET": _fillet, "CHAMFER": _chamfer, "ERASE": _erase,
        "EXPLODE": _explode, "JOIN": _join, "STRETCH": _stretch, "BREAK": _break,
        "ZOOM_WIN": _zoom, "ZOOM_EXT": _zoom, "PAN": _pan, "REGEN": _regen,
        "REDRAW": _regen, "GCODE": _gcode, "GCODEGEN": _gcode, "NEW": _new,
        "OPEN": _open, "QSAVE": _save, "SAVE": _save, "SAVEAS": _saveas,
        "PLOT": _plot, "HATCH": _hatch, "DIMLINEAR": _dim, "DIMRAD": _dim,
        "DIMDIA": _dim, "DIMANG": _dim, "LEADER": _leader, "PURGE": _erase,
        "LAYER": _layer, "UNDO": _copy, "REDO": _move,
    }


class RibbonButton(QPushButton):
    def __init__(self, icon, label, tooltip, parent=None):
        super().__init__(parent)
        self.setIcon(icon)
        self.setText(label)
        self.setToolTip(tooltip)
        self.setIconSize(QSize(34, 34))
        self.setMinimumWidth(64)
        self.setMaximumWidth(96)
        self.setMinimumHeight(56)


class Ribbon(QTabWidget):
    def __init__(self, dispatch, parent=None):
        super().__init__(parent)
        self.setMovable(False)
        self.setTabPosition(QTabWidget.TabPosition.North)
        self.dispatch = dispatch
        self.factory = IconFactory()
        self._build()

    def _panel(self, title):
        w = QFrame()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)
        lab = QLabel(title)
        lab.setStyleSheet("QLabel { color:#9ec1ff; font-weight:bold; font-size:10px; }")
        v.addWidget(lab)
        grid = QHBoxLayout()
        grid.setSpacing(4)
        v.addLayout(grid)
        return w, grid

    def _add_button(self, grid, cmd, label=None, tooltip=None):
        label = label or cmd
        tooltip = tooltip or f"{cmd}  ({label})"
        btn = RibbonButton(self.factory.icon(cmd), label, tooltip)
        btn.clicked.connect(lambda checked=False, c=cmd: self.dispatch(c))
        grid.addWidget(btn)

    def _tab(self, title, panels):
        tab = QWidget()
        h = QHBoxLayout(tab)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(8)
        for ptitle, buttons in panels:
            panel, grid = self._panel(ptitle)
            for b in buttons:
                if isinstance(b, tuple):
                    self._add_button(grid, *b)
                else:
                    self._add_button(grid, b)
            h.addWidget(panel)
        h.addStretch(1)
        self.addTab(tab, title)

    def _build(self):
        self._tab("Draw", [
            ("Draw", [("LINE", "Line"), ("CIRCLE", "Circle"), ("ARC", "Arc"),
                      ("PLINE", "Pline"), ("RECTANG", "Rect"), ("POLYGON", "Pol")]),
            ("More", [("ELLIPSE", "Ellipse"), ("POINT", "Point"), ("TEXT", "Text"),
                      ("MTEXT", "MText"), ("HATCH", "Hatch"), ("SOLID", "Solid")]),
        ])
        self._tab("Modify", [
            ("Clipboard", [("COPY", "Copy"), ("MOVE", "Move"), ("ROTATE", "Rot"),
                           ("SCALE", "Scale"), ("MIRROR", "Mir"), ("ARRAY", "Arr")]),
            ("Edit", [("OFFSET", "Offset"), ("TRIM", "Trim"), ("EXTEND", "Ext"),
                      ("FILLET", "Fil"), ("CHAMFER", "Cha"), ("STRETCH", "Str")]),
            ("Cleanup", [("BREAK", "Break"), ("JOIN", "Join"), ("EXPLODE", "Xpl"),
                         ("ERASE", "Erase"), ("PURGE", "Purge")]),
        ])
        self._tab("Annotate", [
            ("Dimension", [("DIMLINEAR", "Dim"), ("DIMRAD", "Rad"), ("DIMDIA", "Dia"),
                           ("DIMANG", "Ang"), ("LEADER", "Lead")]),
            ("Text", [("TEXT", "Text"), ("MTEXT", "MText")]),
        ])
        self._tab("View", [
            ("Zoom / Pan", [("ZOOM_WIN", "Win"), ("ZOOM_EXT", "Ext"),
                            ("PAN", "Pan"), ("REGEN", "Regen"), ("REDRAW", "Redraw")]),
        ])
        self._tab("Tools", [
            ("Cam", [("GCODE", "G-Code")]),
            ("Utility", [("LAYER", "Layer"), ("LIST", "List"), ("PROPERTIES", "Props"),
                         ("MEASURE", "Meas"), ("UNDO", "Undo"), ("REDO", "Redo")]),
        ])
        self._tab("File", [
            ("File", [("NEW", "New"), ("OPEN", "Open"), ("QSAVE", "Save"),
                      ("SAVEAS", "Save As"), ("PLOT", "Plot")]),
        ])
