"""
constraint_manager.py
SolidWorks-style Constraint Manager + manual constraint adder.

Lists every geometric/dimensional constraint and design variable in the
drawing, lets you delete or toggle them, and add MANUAL constraints
(COINCIDENT, PARALLEL, PERPENDICULAR, TANGENT, CONCENTRIC, MIDPOINT,
HORIZONTAL, VERTICAL, EQUAL, DISTANCE, RADIUS, DIAMETER, ANGLE) by picking
entities on the canvas.
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                               QListWidgetItem, QPushButton, QLabel, QComboBox,
                               QMessageBox)
from PyQt6.QtCore import Qt

import constraints as C


class ConstraintManager(QDialog):
    def __init__(self, drawing, canvas, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Constraint Manager")
        self.resize(560, 480)
        self.drawing = drawing
        self.canvas = canvas

        root = QVBoxLayout(self)

        root.addWidget(QLabel("Geometric / Dimensional constraints:"))
        self.clist = QListWidget()
        self.clist.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        root.addWidget(self.clist, 1)

        cbar = QHBoxLayout()
        self.btn_del = QPushButton("Delete")
        self.btn_del.clicked.connect(self._delete)
        self.btn_solve = QPushButton("Rebuild (solve)")
        self.btn_solve.clicked.connect(self._solve)
        cbar.addWidget(self.btn_del)
        cbar.addWidget(self.btn_solve)
        cbar.addStretch(1)
        root.addLayout(cbar)

        root.addWidget(QLabel("Design variables (parameters):"))
        self.vlist = QListWidget()
        root.addWidget(self.vlist, 1)
        vbar = QHBoxLayout()
        self.btn_delvar = QPushButton("Delete Variable")
        self.btn_delvar.clicked.connect(self._delete_var)
        vbar.addWidget(self.btn_delvar)
        vbar.addStretch(1)
        root.addLayout(vbar)

        root.addWidget(QLabel("Add manual constraint:"))
        add = QHBoxLayout()
        self.cb_type = QComboBox()
        self.cb_type.addItems(["COINCIDENT", "PARALLEL", "PERPENDICULAR",
                                "TANGENT", "CONCENTRIC", "MIDPOINT",
                                "HORIZONTAL", "VERTICAL", "EQUAL",
                                "DISTANCE", "RADIUS", "DIAMETER", "ANGLE"])
        self.btn_add = QPushButton("Add (pick on canvas)")
        self.btn_add.clicked.connect(self._start_add)
        add.addWidget(self.cb_type, 1)
        add.addWidget(self.btn_add)
        root.addLayout(add)
        self.lbl_hint = QLabel("")
        root.addWidget(self.lbl_hint)

        self._pending_add = None
        self._refresh()

    def _refresh(self):
        self.clist.clear()
        for con in self.drawing.constraints:
            item = QListWidgetItem(f"[{con.KIND}] {con.description()}")
            item.setData(Qt.ItemDataRole.UserRole, con)
            self.clist.addItem(item)
        self.vlist.clear()
        for name, var in self.drawing.variables.items():
            item = QListWidgetItem(f"{name} = {var.value:g}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.vlist.addItem(item)

    def _delete(self):
        for item in self.clist.selectedItems():
            con = item.data(Qt.ItemDataRole.UserRole)
            self.drawing.remove_constraint(con)
        self.drawing.solve_constraints()
        if self.canvas:
            self.canvas.update()
        self._refresh()

    def _delete_var(self):
        for item in self.vlist.selectedItems():
            name = item.data(Qt.ItemDataRole.UserRole)
            self.drawing.variables.pop(name, None)
        self.drawing.solve_constraints()
        if self.canvas:
            self.canvas.update()
        self._refresh()

    def _solve(self):
        res = self.drawing.solve_constraints()
        if self.canvas:
            self.canvas.update()
        QMessageBox.information(self, "Rebuild", f"Residual after solve: {res:.4g}")

    def _start_add(self):
        t = self.cb_type.currentText()
        need = 2 if t in ("COINCIDENT", "PARALLEL", "PERPENDICULAR", "EQUAL",
                          "CONCENTRIC", "TANGENT", "MIDPOINT", "DISTANCE",
                          "ANGLE") else 1
        self._pending_add = (t, [], need)
        self.lbl_hint.setText(f"Click {need} entity(ies) on the canvas for {t}...")
        if self.canvas:
            self.canvas.begin_manual_constraint(self._on_picked)

    def _on_picked(self, ents):
        if not self._pending_add:
            return
        t, picked, need = self._pending_add
        picked.extend(ents)
        if len(picked) < need:
            self.lbl_hint.setText(f"Need {need - len(picked)} more...")
            return
        self._pending_add = None
        self.lbl_hint.setText("")
        con = self._build(t, picked)
        if con is not None:
            self.drawing.push_undo()
            self.drawing.add_constraint(con)
            self.drawing.solve_constraints()
            if self.canvas:
                self.canvas.update()
        self._refresh()

    def _build(self, t, ents):
        cls = C.CONSTRAINT_TYPES[t]
        try:
            if t == "COINCIDENT":
                return cls(ents[0], "p1", ents[1], "p1")
            if t in ("HORIZONTAL", "VERTICAL"):
                return cls(ents[0])
            if t in ("PARALLEL", "PERPENDICULAR", "EQUAL", "CONCENTRIC", "TANGENT"):
                return cls(ents[0], ents[1])
            if t == "MIDPOINT":
                return cls(ents[0], ents[1], "p1")
            if t == "DISTANCE":
                val, ok = self._ask_value("Distance value:")
                if not ok:
                    return None
                return cls(ents[0], "p1", ents[1], "p1", value=val)
            if t in ("RADIUS", "DIAMETER"):
                val, ok = self._ask_value("Radius/diameter value:")
                if not ok:
                    return None
                return cls(ents[0], value=val, diameter=(t == "DIAMETER"))
            if t == "ANGLE":
                val, ok = self._ask_value("Angle (deg):")
                if not ok:
                    return None
                return cls(ents[0], ents[1], value=val)
        except Exception as e:
            QMessageBox.warning(self, "Constraint", f"Could not add: {e}")
            return None
        return None

    def _ask_value(self, prompt):
        from PyQt6.QtWidgets import QInputDialog
        val, ok = QInputDialog.getDouble(self, "Value", prompt, 10.0, -1e9, 1e9, 3)
        return val, ok
