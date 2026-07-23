"""
dim_dialog.py
Small value-entry panel for dimensions (SolidWorks-style "driven dimension").
Shown (1) immediately after a dimension is created so you can type its value,
and (2) on double-click of an existing dimension to edit it later.

When "Drive geometry" is checked the typed value is written back into the
source entity via Dimension.apply_value, so the modeled geometry resizes to
match the dimension.
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QDoubleSpinBox, QCheckBox, QPushButton, QComboBox)
from PyQt6.QtCore import Qt

from entities import Dimension


def _fmt_unit(subtype):
    if subtype in ("radius", "radial", "diameter"):
        return "R" if subtype != "diameter" else ""
    if subtype == "angular":
        return "deg"
    return "mm"


class DimEditDialog(QDialog):
    def __init__(self, dim, parent=None):
        super().__init__(parent)
        self.dim = dim
        self.setWindowTitle("Dimension")
        self.setMinimumWidth(280)
        root = QVBoxLayout(self)

        sub = dim.subtype
        unit = _fmt_unit(sub)
        root.addWidget(QLabel(f"Type: {sub.capitalize()}"))

        row = QHBoxLayout()
        row.addWidget(QLabel("Measured:"))
        self.lbl_meas = QLabel(f"{dim.measurement:.3f} {unit}")
        row.addWidget(self.lbl_meas)
        row.addStretch(1)
        root.addLayout(row)

        vrow = QHBoxLayout()
        vrow.addWidget(QLabel("Value:"))
        self.spin = QDoubleSpinBox()
        self.spin.setRange(-1e9, 1e9)
        self.spin.setDecimals(4)
        self.spin.setValue(dim.measurement)
        # angular dims are in degrees; lengths in model units
        vrow.addWidget(self.spin, 1)
        root.addLayout(vrow)

        self.drive = QCheckBox("Drive geometry (resize entity to this value)")
        self.drive.setChecked(True)
        root.addWidget(self.drive)

        self.err = QLabel("")
        self.err.setStyleSheet("QLabel { color:#ff8080; }")
        root.addWidget(self.err)

        btns = QHBoxLayout()
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        root.addLayout(btns)
        self.spin.selectAll()
        self.spin.setFocus()

    def apply(self):
        value = self.spin.value()
        if not self.drive.isChecked():
            return False  # just display, don't change geometry
        try:
            self.dim.apply_value(value)
            return True
        except Exception as e:
            self.err.setText(f"Could not apply: {e}")
            return False
