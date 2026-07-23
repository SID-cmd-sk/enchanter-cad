"""
main.py
Entry point. AutoCAD-style main window: drawing canvas + command-line bar
(bottom, like AutoCAD's), toolbar with common commands + 1-click G-CODE
button, layer box, coordinate readout, and full A-Z command alias support
typed into the command line.
"""
import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                              QLineEdit, QToolBar, QStatusBar, QLabel, QComboBox,
                              QFileDialog, QMessageBox, QPlainTextEdit, QSplitter,
                              QCompleter, QAbstractSpinBox, QListWidget)
from PyQt6.QtGui import QAction, QFont, QKeySequence, QKeyEvent
from PyQt6.QtCore import Qt, QEvent

from entities import Drawing
from canvas import Canvas
from commands import COMMANDS, Prompt
from command_table import resolve
import io_dxf
from gcode_dialog import GCodeDialog
from ribbon import Ribbon
from constraint_manager import ConstraintManager
import testlog


APP_STYLESHEET = """
QMainWindow, QWidget { background-color:#1e1e22; color:#e6e6e6; }
QMenuBar { background:#2a2a30; }
QMenuBar::item:selected { background:#3a6ea5; }
QStatusBar { background:#2a2a30; }
QTabWidget::pane { border:1px solid #3a3a40; top:-1px; }
QTabBar::tab { background:#2a2a30; color:#c8c8c8; padding:6px 16px;
               border:1px solid #3a3a40; border-bottom:none; border-top-left-radius:5px;
               border-top-right-radius:5px; }
QTabBar::tab:selected { background:#3a3d44; color:#ffffff; }
QTabBar::tab:hover { background:#33333a; }
QFrame { background:transparent; }
QComboBox, QLineEdit, QPlainTextEdit { background:#2a2a30; border:1px solid #3a3a40;
                                        border-radius:4px; padding:2px 4px; color:#e6e6e6; }
QComboBox QAbstractItemView { background:#2a2a30; selection-background-color:#3a6ea5; }
QPushButton { background:#2e2e34; border:1px solid #3a3a40; border-radius:5px;
              padding:4px 8px; color:#e6e6e6; }
QPushButton:hover { background:#3a3d44; }
QPushButton:pressed { background:#3a6ea5; }
QToolBar { background:#26262b; border:none; spacing:2px; }
QLabel { color:#c8c8c8; }
QScrollArea, QListWidget { background:#26262b; }
QTabWidget::tab-bar { alignment:left; }
"""


class CommandLineEdit(QLineEdit):
    """Bottom command bar - AutoCAD 'Type a command' behavior."""
    def __init__(self, main_win):
        super().__init__()
        self.main_win = main_win
        self.setFont(QFont("Consolas", 11))
        self.setPlaceholderText("Type a command (e.g. L, C, M, GCODE) and press Enter...")
        self.history = []
        self.hist_idx = -1

        # Mod 3: inline command suggestions (type "c" -> all c* commands)
        from command_table import COMMAND_ALIASES
        suggestions = set()
        for alias, (full, desc) in COMMAND_ALIASES.items():
            suggestions.add(alias)
            suggestions.add(full)
        completer = QCompleter(sorted(suggestions))
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCompleter(completer)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # If a G-code entity-pick is in progress, Enter confirms the
            # selection and resumes the (hidden) G-code dialog.
            if getattr(self.main_win, "_gcode_pick_dlg", None) is not None:
                self.main_win.finish_gcode_entity_pick()
                return
            text = self.text().strip()
            self.history.append(text)
            self.hist_idx = len(self.history)
            self.clear()
            self.main_win.handle_command_line(text)
            return
        if ev.key() == Qt.Key.Key_Space:
            # Space acts like Enter (AutoCAD workflow) UNLESS there is an active
            # command awaiting a TEXT/POINT value - then let the canvas consume
            # it as a delimiter/confirm.  Plain space-with-no-text repeats the
            # previous command (intentional, not accidental).
            if getattr(self.main_win, "_gcode_pick_dlg", None) is not None:
                self.main_win.finish_gcode_entity_pick()
                return
            text = self.text().strip()
            if text or self.main_win.canvas.active_gen:
                self.history.append(text)
                self.hist_idx = len(self.history)
                self.clear()
                self.main_win.handle_command_line(text)
            else:
                self.main_win.repeat_last_command()
            return
        if ev.key() == Qt.Key.Key_Escape:
            self.clear()
            if getattr(self.main_win, "_gcode_pick_dlg", None) is not None:
                self.main_win.cancel_gcode_entity_pick()
                return
            self.main_win.canvas.cancel_command()
            return
        if ev.key() == Qt.Key.Key_Delete:
            if not self.main_win.canvas.active_gen:
                sel = self.main_win.canvas.drawing.selected()
                if sel:
                    self.main_win.canvas.drawing.push_undo()
                    for e in sel:
                        self.main_win.canvas.drawing.remove(e)
                    self.main_win.canvas.update()
                    self.main_win.log_message(f"Erased {len(sel)} object(s).")
                    return
        if ev.key() == Qt.Key.Key_Up and self.history:
            self.hist_idx = max(0, self.hist_idx - 1)
            self.setText(self.history[self.hist_idx])
            return
        if ev.key() == Qt.Key.Key_Down and self.history:
            self.hist_idx = min(len(self.history), self.hist_idx + 1)
            self.setText(self.history[self.hist_idx] if self.hist_idx < len(self.history) else "")
            return
        super().keyPressEvent(ev)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyCAD - AutoCAD-workflow CAD/CAM  (Sidharth's build)")
        self.resize(1400, 900)

        self.drawing = Drawing()
        self.canvas = Canvas(self.drawing)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.canvas)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        self.log.setFont(QFont("Consolas", 9))
        splitter.addWidget(self.log)
        splitter.setSizes([760, 110])
        layout.addWidget(splitter)

        self.cmdline = CommandLineEdit(self)
        layout.addWidget(self.cmdline)
        self.setCentralWidget(central)

        self._build_ribbon()
        layout.insertWidget(0, self.ribbon)

        self._build_toolbar()
        self._build_statusbar()
        self._build_menu()

        self.canvas.status_message.connect(self.log_message)
        self.canvas.coords_changed.connect(self.update_coords)
        self.canvas.command_finished.connect(self.on_command_finished)
        self.canvas.prompt_changed.connect(self.on_prompt_changed)

        self.log_message("Ready. Type a command below (see full A-Z list in Help > Command Reference).")
        self.last_command = None
        self._gcode_pick_dlg = None
        self.cmdline.setFocus()

    # ---------------------------------------------------------- UI build

    def _build_toolbar(self):
        # Slim secondary toolbar: keep the layer selector (ribbon holds the
        # command buttons). A quick G-CODE button is also kept for convenience.
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        gcode_act = QAction("\u2699 G-CODE", self)
        gcode_act.setToolTip("Generate G-code from selected/all geometry (ported from GCODEGEN_.lsp)")
        gcode_act.triggered.connect(self.open_gcode_dialog)
        tb.addAction(gcode_act)

        tb.addSeparator()
        tb.addWidget(QLabel("  Layer: "))
        self.layer_box = QComboBox()
        self.layer_box.setEditable(True)
        self.layer_box.addItem("0")
        self.layer_box.currentTextChanged.connect(self.on_layer_changed)
        tb.addWidget(self.layer_box)

    def _build_ribbon(self):
        self.ribbon = Ribbon(self.dispatch)
        self.ribbon.setMaximumHeight(132)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.coord_label = QLabel("X: 0.000  Y: 0.000")
        self.prompt_label = QLabel("")
        sb.addPermanentWidget(self.coord_label)
        sb.addWidget(self.prompt_label, 1)

    def _build_menu(self):
        m = self.menuBar()
        filem = m.addMenu("&File")
        for label, slot, shortcut in [
            ("New", self.new_drawing, "Ctrl+N"),
            ("Open...", self.open_drawing, "Ctrl+O"),
            ("Save", self.save_drawing, "Ctrl+S"),
            ("Save As...", self.save_drawing_as, "Ctrl+Shift+S"),
        ]:
            act = QAction(label, self)
            act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(slot)
            filem.addAction(act)
        filem.addSeparator()
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close)
        filem.addAction(exit_act)

        editm = m.addMenu("&Edit")
        undo_act = QAction("Undo", self); undo_act.setShortcut("Ctrl+Z")
        undo_act.triggered.connect(lambda: self.dispatch("UNDO"))
        editm.addAction(undo_act)
        redo_act = QAction("Redo", self); redo_act.setShortcut("Ctrl+Y")
        redo_act.triggered.connect(lambda: self.dispatch("REDO"))
        editm.addAction(redo_act)

        toolsm = m.addMenu("&Tools")
        gc_act = QAction("G-Code Generator...", self)
        gc_act.triggered.connect(self.open_gcode_dialog)
        toolsm.addAction(gc_act)
        cm_act = QAction("Constraint Manager...", self)
        cm_act.triggered.connect(self.open_constraint_manager)
        toolsm.addAction(cm_act)

        helpm = m.addMenu("&Help")
        ref_act = QAction("Command Reference", self)
        ref_act.triggered.connect(self.show_command_reference)
        helpm.addAction(ref_act)

    # ---------------------------------------------------------- command dispatch

    def eventFilter(self, obj, ev):
        # Mod 2: let commands run regardless of focus. Forward printable keys
        # plus Enter/Space/Tab to the command line whenever no modal dialog is
        # open and the focused widget isn't already a text-entry control.
        if ev.type() == QEvent.Type.KeyPress:
            if QApplication.activeModalWidget() is not None:
                return False
            fw = QApplication.focusWidget()
            if isinstance(fw, (QLineEdit, QPlainTextEdit, QComboBox,
                               QAbstractSpinBox, QListWidget)):
                return False
            key = ev.key()
            text = ev.text()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                       Qt.Key.Key_Space, Qt.Key.Key_Tab):
                QApplication.postEvent(self.cmdline,
                                       QKeyEvent(ev.type(), key, ev.modifiers(), text))
                return True
            if text and text.isprintable() and key != Qt.Key.Key_Escape:
                QApplication.postEvent(self.cmdline,
                                       QKeyEvent(ev.type(), key, ev.modifiers(), text))
                return True
        return super().eventFilter(obj, ev)

    def handle_command_line(self, text):
        text = text.strip()
        if text:
            testlog.log(f"CMD_INPUT: {text!r}")
        if not text:
            if self.canvas.active_gen:
                self.canvas.feed_text("")
            else:
                self.repeat_last_command()
            return
        if self.canvas.active_gen:
            # A command is mid-prompt (point/text/selection).  The typed text is
            # the prompt VALUE, NOT a new command - otherwise typing "S" for a
            # SINGLE/DOUBLE font choice would wrongly launch STRETCH.  To abort a
            # running command, press Esc (wired to canvas.cancel_command).
            self.canvas.feed_text(text)
            return
        name, desc = resolve(text)
        if name is None:
            self.log_message(f'Unknown command: "{text}"')
            return
        self.dispatch(name)

    def repeat_last_command(self):
        """Re-run the last command when the command line is empty and Enter or
        Space is pressed (AutoCAD 'repeat last command' behavior).  Dialog-only
        commands (file open/save, G-code dialog) are not auto-repeated to avoid
        popping modal windows unexpectedly."""
        if not getattr(self, "last_command", None):
            return
        skip = {"NEW", "OPEN", "QSAVE", "SAVE", "SAVEAS", "GCODE", "GCODEGEN",
                "MANAGER", "ZOOM_EXT"}
        if self.last_command in skip:
            return
        self.dispatch(self.last_command)

    def dispatch(self, name):
        testlog.log_start(name)
        self._log_name = name
        self.last_command = name
        try:
            if name == "ZOOM_EXT":
                self.canvas.fit_view()
                self.log_message("Zoomed to extents.")
                testlog.log_end(name, "zoom")
                return
            if name == "NEW":
                self.new_drawing(); testlog.log_end(name, "new"); return
            if name == "OPEN":
                self.open_drawing(); testlog.log_end(name, "open"); return
            if name in ("QSAVE", "SAVE"):
                self.save_drawing(); testlog.log_end(name, "save"); return
            if name == "SAVEAS":
                self.save_drawing_as(); testlog.log_end(name, "saveas"); return
            if name in ("GCODE", "GCODEGEN"):
                self.open_gcode_dialog(); testlog.log_end(name, "gcode dialog"); return
            if name == "MANAGER":
                self.open_constraint_manager(); testlog.log_end(name, "manager"); return

            gen_func = COMMANDS.get(name)
            if not gen_func:
                full, desc = resolve(name)
                if full:
                    self.log_message(f'"{full}" is recognized but not implemented in this build yet '
                                      f'({desc}). Core drawing/modify/G-code commands are fully working.')
                else:
                    self.log_message(f'Unknown command: "{name}"')
                testlog.log_end(name, "unknown/not-implemented")
                return
            self.last_command = name
            self.canvas.start_command(name, gen_func)
            self.log_message(f"Command: {name}")
            # generator commands: END is logged in on_command_finished
        except Exception as e:
            testlog.log_error(name, e)
            self.log_message(f"Error: {e}")

    def on_prompt_changed(self, message, kind):
        self.prompt_label.setText(message)
        self.cmdline.setFocus()

    def on_command_finished(self, message):
        self.log_message(message)
        self.prompt_label.setText("")
        self._refresh_layers()
        name = getattr(self, "_log_name", None)
        if name:
            testlog.log_end(name, message)
        self.cmdline.setFocus()

    def log_message(self, msg):
        self.log.appendPlainText(msg)

    def update_coords(self, x, y):
        self.coord_label.setText(f"X: {x:8.3f}  Y: {y:8.3f}")

    def on_layer_changed(self, name):
        if name and name not in self.drawing.layers:
            self.drawing.layers[name] = {"color": 7, "on": True, "frozen": False}
        if name:
            self.drawing.current_layer = name

    def _refresh_layers(self):
        current = self.layer_box.currentText()
        self.layer_box.blockSignals(True)
        self.layer_box.clear()
        self.layer_box.addItems(sorted(self.drawing.layers.keys()))
        idx = self.layer_box.findText(self.drawing.current_layer)
        if idx >= 0:
            self.layer_box.setCurrentIndex(idx)
        self.layer_box.blockSignals(False)

    # ---------------------------------------------------------- file ops

    def new_drawing(self):
        self.drawing = Drawing()
        self.canvas.drawing = self.drawing
        self.canvas.fit_view()
        self._refresh_layers()
        self.log_message("New drawing.")

    def open_drawing(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Drawing", "", "CAD files (*.dxf *.dwg);;All files (*.*)")
        if not path:
            return
        try:
            self.drawing = io_dxf.load_drawing(path)
            self.canvas.drawing = self.drawing
            self.canvas.fit_view()
            self._refresh_layers()
            rep = getattr(self.drawing, "_import_report", None)
            if rep:
                self.log_message(f"Opened {path}  ({len(self.drawing.entities)} entities, "
                                 f"{rep[0]} imported, {rep[1]} unsupported skipped)")
            else:
                self.log_message(f"Opened {path}  ({len(self.drawing.entities)} entities)")
        except io_dxf.DWGSupportError as e:
            QMessageBox.warning(self, "DWG support", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))

    def save_drawing(self):
        if self.drawing.filepath:
            self._save_to(self.drawing.filepath)
        else:
            self.save_drawing_as()

    def save_drawing_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Drawing As", "drawing.dxf",
                                               "DXF (*.dxf);;DWG (*.dwg)")
        if path:
            self._save_to(path)

    def _save_to(self, path):
        try:
            io_dxf.save_drawing(self.drawing, path)
            self.log_message(f"Saved {path}")
        except io_dxf.DWGSupportError as e:
            QMessageBox.warning(self, "DWG support", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    # ---------------------------------------------------------- tools

    def open_gcode_dialog(self):
        if not self.drawing.entities:
            QMessageBox.information(self, "G-Code", "Drawing is empty - draw or open geometry first.")
            return
        dlg = GCodeDialog(self.drawing, self)
        dlg.exec()

    # ---- G-code "pick entities on canvas" handshake ----
    # The G-code dialog hides itself and asks the user to window/drag-select
    # entities on the canvas. Enter (or Space) confirms; Escape cancels.
    def begin_gcode_entity_pick(self, dlg):
        self._gcode_pick_dlg = dlg
        self.log_message("Select entities to machine, then press Enter "
                         "(or Space) to resume G-code. Esc cancels.")
        self.cmdline.setFocus()

    def finish_gcode_entity_pick(self):
        dlg = self._gcode_pick_dlg
        self._gcode_pick_dlg = None
        if dlg is not None:
            dlg.resume_from_canvas()
            self.log_message("G-code selection applied - dialog resumed.")

    def cancel_gcode_entity_pick(self):
        dlg = self._gcode_pick_dlg
        self._gcode_pick_dlg = None
        if dlg is not None:
            dlg.show()
            dlg.activateWindow()
            self.log_message("G-code entity pick cancelled.")

    def open_constraint_manager(self):
        dlg = ConstraintManager(self.drawing, self.canvas, self)
        dlg.exec()

    def show_command_reference(self):
        from command_table import COMMAND_ALIASES
        seen = set()
        lines = []
        for alias, (full, desc) in sorted(COMMAND_ALIASES.items()):
            if full in seen:
                continue
            seen.add(full)
            impl = "\u2713" if full in COMMANDS or full in ("QSAVE", "OPEN", "SAVEAS", "NEW", "GCODEGEN") else " "
            lines.append(f"[{impl}] {alias:<10} {full:<22} {desc}")
        QMessageBox.information(self, "Command Reference (\u2713 = implemented)", "\n".join(lines[:60]) +
                                 f"\n... {len(lines)} total commands. Full list in command_table.py")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    win = MainWindow()
    win.show()
    win.cmdline.setFocus()
    app.installEventFilter(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
