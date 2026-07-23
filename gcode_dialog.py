"""
gcode_dialog.py
PyQt6 replacement for the LSP's DCL dialog, organised into grouped
category forms (SolidCAM-style) with a clickable toolpath preview.

Categories: Selection & Start, Tool Geometry, Cutting, Levels, Passes,
Leads, Tabs & Bridges, Advanced.

Supports selecting SPECIFIC entities (not just "all"), picking the start
point interactively in the preview, and the extended CAM parameters:
kerf width, pierce dwell, overcut, inner-first ordering, tabs/bridges.
"""
import math
from PyQt6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox, QCheckBox,
                              QPushButton, QHBoxLayout, QVBoxLayout, QLabel,
                              QFileDialog, QPlainTextEdit, QWidget, QGroupBox,
                              QListWidget, QListWidgetItem, QStackedWidget,
                              QMessageBox, QAbstractItemView)
from PyQt6.QtGui import QPainter, QPen, QColor, QFont
from PyQt6.QtCore import Qt, pyqtSignal

import gcode as gc
import testlog


def _le(default, tooltip=None):
    w = QLineEdit(str(default))
    if tooltip:
        w.setToolTip(tooltip)
    return w


class PreviewWidget(QWidget):
    start_picked = pyqtSignal(object)  # world (x, y) or None

    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 320)
        self.entities = []
        self.origin = (0.0, 0.0)
        self.start_pt = None     # world coords
        self.pick_mode = False
        self._view = None
        self.zoom = 1.0

    def zoom_by(self, factor):
        self.zoom = max(0.05, min(self.zoom * factor, 200.0))
        self.update()

    def reset_zoom(self):
        self.zoom = 1.0
        self.update()

    def set_entities(self, entities, origin):
        self.entities = entities
        self.origin = origin
        self.update()

    def set_start(self, pt):
        self.start_pt = pt
        self.update()

    def compute_view(self):
        allpts = []
        for e in self.entities:
            raw = gc.entity_to_verts_raw(e)
            if not raw:
                continue
            shifted = gc.shift_verts(raw, self.origin)
            for i in range(len(shifted) - 1):
                p1, b1 = shifted[i]
                p2, _ = shifted[i + 1]
                pts = gc.bulge_to_arc_pts(p1, p2, b1, 12)
                allpts.extend(pts)
        if len(allpts) < 2:
            return None
        xs = [pt[0] for pt in allpts]; ys = [pt[1] for pt in allpts]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        w = max(maxx - minx, 1e-6); h = max(maxy - miny, 1e-6)
        tw, th = self.width(), self.height()
        scale = min(tw * 0.85 / w, th * 0.85 / h)
        ox = (tw - w * scale) / 2.0
        oy = (th - h * scale) / 2.0
        return dict(scale=scale, ox=ox, oy=oy, minx=minx, miny=miny, w=w, h=h)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(20, 20, 22))
        self._view = self.compute_view()
        if self._view is None:
            p.setPen(QPen(QColor(150, 150, 150)))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "No geometry selected\n(choose entities on the left)")
            p.end()
            return

        # apply user zoom about the widget centre
        base = self._view
        scale = base["scale"] * self.zoom
        tw, th = self.width(), self.height()
        cxw = base["minx"] + base["w"] / 2.0
        cyw = base["miny"] + base["h"] / 2.0
        scx, scy = tw / 2.0, th / 2.0
        ox = scx - (cxw - base["minx"]) * scale
        oy = th - scy - (cyw - base["miny"]) * scale
        self._view = dict(scale=scale, ox=ox, oy=oy,
                          minx=base["minx"], miny=base["miny"], w=base["w"], h=base["h"])

        def to_screen(pt):
            v = self._view
            return (v["ox"] + (pt[0] - v["minx"]) * v["scale"],
                    self.height() - (v["oy"] + (pt[1] - v["miny"]) * v["scale"]))

        # source geometry (dim gray)
        p.setPen(QPen(QColor(90, 90, 95), 1))
        for e in self.entities:
            raw = gc.entity_to_verts_raw(e)
            if not raw:
                continue
            shifted = gc.shift_verts(raw, self.origin)
            pts = []
            for i in range(len(shifted) - 1):
                p1, b1 = shifted[i]; p2, _ = shifted[i + 1]
                arcpts = gc.bulge_to_arc_pts(p1, p2, b1, 12)
                pts.extend(arcpts if not pts else arcpts[1:])
            for i in range(len(pts) - 1):
                a = to_screen(pts[i]); b = to_screen(pts[i + 1])
                p.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))

        # marker for start point
        if self.start_pt is not None:
            s = to_screen(self.start_pt)
            p.setPen(QPen(QColor(80, 180, 255), 2))
            p.setBrush(QColor(80, 180, 255))
            p.drawEllipse(int(s[0]) - 5, int(s[1]) - 5, 10, 10)
            p.setPen(QPen(QColor(80, 180, 255)))
            p.drawText(int(s[0]) + 8, int(s[1]) + 4, "start")

        p.setPen(QPen(QColor(120, 120, 120)))
        hint = "Click preview to pick start point" if self.pick_mode else ""
        if hint:
            p.drawText(8, self.height() - 10, hint)
        p.end()

    def mousePressEvent(self, ev):
        if not self.pick_mode or self._view is None:
            return
        x = ev.position().x(); y = ev.position().y()
        v = self._view
        wx = (x - v["ox"]) / v["scale"] + v["minx"]
        wy = v["miny"] + (self.height() - y - v["oy"]) / v["scale"]
        self.start_pt = (wx, wy)
        self.start_picked.emit(self.start_pt)
        self.update()

    def wheelEvent(self, ev):
        if self._view is None:
            return
        factor = 1.15 if ev.angleDelta().y() > 0 else 1.0 / 1.15
        self.zoom_by(factor)


class GCodeDialog(QDialog):
    CATEGORIES = [
        "Selection & Start",
        "Tool Geometry",
        "Cutting",
        "Levels",
        "Passes",
        "Leads",
        "Tabs & Bridges",
        "Advanced",
    ]

    def __init__(self, drawing, parent=None):
        super().__init__(parent)
        self.setWindowTitle("G-CODE Generator")
        self.resize(820, 600)
        self.drawing = drawing
        current_sel = drawing.selected()
        self.selected_ids = {id(e) for e in current_sel} if current_sel else {id(e) for e in drawing.entities}

        root = QHBoxLayout(self)

        # ---- left: category navigator + stacked forms
        left = QVBoxLayout()
        self.cats = QListWidget()
        self.cats.addItems(self.CATEGORIES)
        self.cats.setMaximumWidth(170)
        self.cats.setCurrentRow(0)
        self.cats.currentRowChanged.connect(self._switch_cat)
        self.stack = QStackedWidget()
        self._build_forms()
        left.addWidget(QLabel("Categories"))
        left.addWidget(self.cats)
        left.addWidget(self.stack, 1)

        # ---- right: preview + output
        right = QVBoxLayout()
        self.preview = PreviewWidget()
        self.preview.start_picked.connect(self._on_start_picked)
        right.addWidget(QLabel("Preview  -  click to set START point (blue)"))
        zoombar = QHBoxLayout()
        self.btn_zoomin = QPushButton("Zoom +")
        self.btn_zoomout = QPushButton("Zoom -")
        self.btn_fit = QPushButton("Fit")
        self.btn_zoomin.clicked.connect(lambda: self.preview.zoom_by(1.2))
        self.btn_zoomout.clicked.connect(lambda: self.preview.zoom_by(1.0 / 1.2))
        self.btn_fit.clicked.connect(self.preview.reset_zoom)
        zoombar.addWidget(self.btn_zoomin)
        zoombar.addWidget(self.btn_zoomout)
        zoombar.addWidget(self.btn_fit)
        zoombar.addStretch(1)
        right.addLayout(zoombar)
        right.addWidget(self.preview, 1)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Generated G-code will appear here...")
        right.addWidget(QLabel("G-code output"))
        right.addWidget(self.output, 1)

        root.addLayout(left, 1)
        root.addLayout(right, 1)

        left.addLayout(self._btn_bar)

        self._last_gcode = None
        self._update_selection_label()
        self.refresh_preview()

    # ---------------------------------------------------------- forms
    def _build_forms(self):
        self.forms = {}
        self._widgets = {}

        # Selection & Start
        w = QWidget(); f = QFormLayout(w)
        self.sel_label = QLabel("")
        self.btn_use_sel = QPushButton("Use current canvas selection")
        self.btn_use_sel.clicked.connect(self._use_canvas_selection)
        self.btn_all = QPushButton("Select ALL geometry")
        self.btn_all.clicked.connect(self._select_all)
        self.btn_pick = QPushButton("Pick start point in preview")
        self.btn_pick.setCheckable(True)
        self.btn_pick.toggled.connect(self._toggle_pick)
        self.startx = _le(0, "Start point X (world). Leave 0,0 or click preview.")
        self.starty = _le(0, "Start point Y (world).")
        self.sequence_inner_first = QCheckBox("Cut inner contours first (islands)")
        f.addRow(self.sel_label)
        f.addRow(self.btn_use_sel)
        f.addRow(self.btn_all)
        f.addRow(self.btn_pick)
        f.addRow("Start X", self.startx)
        f.addRow("Start Y", self.starty)
        f.addRow("", self.sequence_inner_first)
        self._widgets["Selection & Start"] = dict(
            startx=self.startx, starty=self.starty,
            sequence_inner_first=self.sequence_inner_first)
        self.stack.addWidget(w); self.forms["Selection & Start"] = w

        # Tool Geometry
        w = QWidget(); f = QFormLayout(w)
        self.tooldia = _le(6, "Cutter diameter (mm)")
        self.toolnum = _le(0, "Tool number (0 = none / T0)")
        self.kerf = _le(0, "Kerf width (mm) - actual cut width; toolpath stays on geometry")
        f.addRow("Tool diameter", self.tooldia)
        f.addRow("Tool number", self.toolnum)
        f.addRow("Kerf width", self.kerf)
        self._widgets["Tool Geometry"] = dict(tooldia=self.tooldia, toolnum=self.toolnum, kerf=self.kerf)
        self.stack.addWidget(w); self.forms["Tool Geometry"] = w

        # Cutting
        w = QWidget(); f = QFormLayout(w)
        self.feed = _le(800, "Cutting feed rate (mm/min)")
        self.plungef = _le(200, "Plunge (Z) feed rate (mm/min)")
        self.rpm = _le(12000, "Spindle speed (RPM)")
        self.coolant = QCheckBox("Coolant on (M08)")
        f.addRow("Feed rate", self.feed)
        f.addRow("Plunge feed", self.plungef)
        f.addRow("Spindle RPM", self.rpm)
        f.addRow("", self.coolant)
        self._widgets["Cutting"] = dict(feed=self.feed, plungef=self.plungef, rpm=self.rpm, coolant=self.coolant)
        self.stack.addWidget(w); self.forms["Cutting"] = w

        # Levels
        w = QWidget(); f = QFormLayout(w)
        self.safez = _le(10, "Upper level / travel height (Safe Z)")
        self.cutz = _le(-2, "Lower level / cutting depth (Cut Z)")
        self.passdepth = _le(0, "Stepdown per pass (0 = single pass)")
        f.addRow("Upper level (Safe Z)", self.safez)
        f.addRow("Lower level (Cut Z)", self.cutz)
        f.addRow("Stepdown", self.passdepth)
        self._widgets["Levels"] = dict(safez=self.safez, cutz=self.cutz, passdepth=self.passdepth)
        self.stack.addWidget(w); self.forms["Levels"] = w

        # Passes
        w = QWidget(); f = QFormLayout(w)
        self.strategy = QComboBox(); self.strategy.addItems(["One-way (retract each pass)", "Zig-zag continuous ramp"])
        self.reverse = QCheckBox("Reverse direction")
        self.interp = QCheckBox("Interpolate arcs to line segments")
        self.interpval = _le(0.1, "Arc interpolation step (mm)")
        f.addRow("Path strategy", self.strategy)
        f.addRow("", self.reverse)
        f.addRow("", self.interp)
        f.addRow("Interp step", self.interpval)
        self._widgets["Passes"] = dict(strategy=self.strategy, reverse=self.reverse,
                                       interp=self.interp, interpval=self.interpval)
        self.stack.addWidget(w); self.forms["Passes"] = w

        # Leads
        w = QWidget(); f = QFormLayout(w)
        self.comp = QComboBox(); self.comp.addItems(["None", "G41 Left", "G42 Right"])
        self.leadtype = QComboBox(); self.leadtype.addItems(["None", "Linear", "Arc"])
        self.leadlen = _le(5, "Lead-in/out length (mm)")
        self.leadangle = _le(45, "Lead-in/out angle (deg)")
        f.addRow("Cutter comp", self.comp)
        f.addRow("Lead type", self.leadtype)
        f.addRow("Lead length", self.leadlen)
        f.addRow("Lead angle", self.leadangle)
        self._widgets["Leads"] = dict(comp=self.comp, leadtype=self.leadtype,
                                      leadlen=self.leadlen, leadangle=self.leadangle)
        self.stack.addWidget(w); self.forms["Leads"] = w

        # Tabs & Bridges
        w = QWidget(); f = QFormLayout(w)
        self.tabs_count = _le(0, "Number of tabs / bridges (0 = none)")
        self.tabs_width = _le(2, "Tab width (mm)")
        self.overcut = _le(0, "Overcut past start on closed loops (mm)")
        f.addRow("Tabs count", self.tabs_count)
        f.addRow("Tabs width", self.tabs_width)
        f.addRow("Overcut", self.overcut)
        self._widgets["Tabs & Bridges"] = dict(tabs_count=self.tabs_count,
                                               tabs_width=self.tabs_width, overcut=self.overcut)
        self.stack.addWidget(w); self.forms["Tabs & Bridges"] = w

        # Advanced
        w = QWidget(); f = QFormLayout(w)
        self.wcs = QComboBox(); self.wcs.addItems(["G54", "G55", "G56", "G57", "G58", "G59"])
        self.homex = _le(0, "Home / park position X")
        self.homey = _le(0, "Home / park position Y")
        self.pierce_dwell = _le(0, "Pierce dwell time (s) - pauses at pierce")
        self.fname = _le("OUTPUT", "Output file base name")
        f.addRow("Work coordinate system", self.wcs)
        f.addRow("Home X", self.homex)
        f.addRow("Home Y", self.homey)
        f.addRow("Pierce dwell", self.pierce_dwell)
        f.addRow("Output file name", self.fname)
        self._widgets["Advanced"] = dict(wcs=self.wcs, homex=self.homex, homey=self.homey,
                                         pierce_dwell=self.pierce_dwell, fname=self.fname)
        self.stack.addWidget(w); self.forms["Advanced"] = w

        # buttons row (always visible)
        self.btn_generate = QPushButton("Generate G-Code")
        self.btn_save = QPushButton("Save As...")
        self.btn_close = QPushButton("Close")
        self.btn_generate.clicked.connect(self.generate)
        self.btn_save.clicked.connect(self.save_as)
        self.btn_close.clicked.connect(self.accept)
        bar = QHBoxLayout()
        bar.addWidget(self.btn_generate); bar.addWidget(self.btn_save); bar.addWidget(self.btn_close)
        # attach button bar to left layout (build after forms)
        self._btn_bar = bar

    def _switch_cat(self, idx):
        self.stack.setCurrentIndex(idx)

    # ---------------------------------------------------------- selection
    def _current_selection(self):
        return [e for e in self.drawing.entities if id(e) in self.selected_ids]

    def _use_canvas_selection(self):
        cur = self.drawing.selected()
        if not cur:
            QMessageBox.information(self, "Selection",
                                    "Nothing selected on the canvas. Use window-select first, or click 'Select ALL'.")
            return
        self.selected_ids = {id(e) for e in cur}
        self._update_selection_label()
        self.refresh_preview()

    def _select_all(self):
        self.selected_ids = {id(e) for e in self.drawing.entities}
        self._update_selection_label()
        self.refresh_preview()

    def _update_selection_label(self):
        total = len(self.drawing.entities)
        n = len(self.selected_ids)
        self.sel_label.setText(f"Selected: {n} of {total} entities")

    # ---------------------------------------------------------- start point
    def _toggle_pick(self, on):
        self.preview.pick_mode = on

    def _on_start_picked(self, pt):
        self.startx.setText(f"{pt[0]:.3f}")
        self.starty.setText(f"{pt[1]:.3f}")
        self.btn_pick.setChecked(False)
        self.preview.pick_mode = False

    # ---------------------------------------------------------- preview
    def _origin(self):
        x1, y1, x2, y2 = self.drawing.bbox()
        return (x1, y1)

    def refresh_preview(self):
        sel = self._current_selection()
        self.preview.set_entities(sel, self._origin())
        try:
            sx = float(self.startx.text()); sy = float(self.starty.text())
            self.preview.set_start((sx, sy))
        except ValueError:
            self.preview.set_start(None)

    # ---------------------------------------------------------- params
    def _collect_params(self):
        params = gc.GCodeParams()
        try:
            params.feed = float(self.feed.text())
            params.rpm = float(self.rpm.text())
            params.safez = float(self.safez.text())
            params.cutz = float(self.cutz.text())
            params.passdepth = float(self.passdepth.text())
            params.plungef = float(self.plungef.text())
            params.tooldia = float(self.tooldia.text())
            params.toolnum = int(float(self.toolnum.text()))
            params.homex = float(self.homex.text())
            params.homey = float(self.homey.text())
            params.leadlen = float(self.leadlen.text())
            params.leadangle = float(self.leadangle.text())
            params.interp_step = float(self.interpval.text())
            params.kerf = float(self.kerf.text())
            params.pierce_dwell = float(self.pierce_dwell.text())
            params.overcut = float(self.overcut.text())
            params.tabs_count = int(float(self.tabs_count.text()))
            params.tabs_width = float(self.tabs_width.text())
            sx = float(self.startx.text()); sy = float(self.starty.text())
            params.start_pt = (sx, sy)
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", f"Check numeric fields: {e}")
            return None
        params.wcs = self.wcs.currentText()
        params.coolant = self.coolant.isChecked()
        params.comp = self.comp.currentIndex()
        params.strategy = self.strategy.currentIndex()
        params.leadtype = self.leadtype.currentIndex()
        params.reverse = self.reverse.isChecked()
        params.interp_on = self.interp.isChecked()
        params.sequence_inner_first = self.sequence_inner_first.isChecked()
        params.origin = self._origin()
        return params

    def generate(self):
        sel = self._current_selection()
        if not sel:
            QMessageBox.warning(self, "No selection",
                                "Select geometry to machine (use 'Use current canvas selection' or 'Select ALL').")
            self.cats.setCurrentRow(0)
            return
        params = self._collect_params()
        if params is None:
            return
        try:
            text, warnings = gc.generate_gcode(sel, params)
        except Exception as e:
            testlog.log_exception("G-code generate", e)
            QMessageBox.critical(self, "G-code error", f"Failed to generate G-code:\n{e}")
            return
        self._last_gcode = text
        self.output.setPlainText(text)
        if warnings:
            QMessageBox.information(self, "Notes", "\n".join(warnings))

    def save_as(self):
        if not self._last_gcode:
            self.generate()
            if not self._last_gcode:
                return
        default_name = (self.fname.text() or "OUTPUT") + ".nc"
        path, _ = QFileDialog.getSaveFileName(self, "Save G-Code", default_name,
                                              "G-Code (*.nc *.tap *.gcode);;All files (*.*)")
        if path:
            with open(path, "w") as f:
                f.write(self._last_gcode)
            QMessageBox.information(self, "Saved", f"G-code saved to:\n{path}")
