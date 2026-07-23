"""
installer_app.py  --  ENCHANTER-CAD 2D self-installer.

A small GUI that copies the bundled application to:
    C:\Program Files\ENCHANTER-CAD 2D
creates Desktop + Start Menu shortcuts, and registers the app in
Control Panel > Programs and Features.

Built as a single-file exe with uac_admin=True so Windows prompts for
admin automatically.  Run it -> click Install -> watch it go.
"""
import os
import sys
import shutil

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QProgressBar, QTextEdit)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap

# The application payload is bundled inside this exe (PyInstaller one-file
# mode extracts it to sys._MEIPASS at runtime).  Fall back to a sibling
# folder when running from source / a folder build.
if getattr(sys, "frozen", False):
    _MEI = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    _SRC = os.path.join(_MEI, "payload", "ENCHANTER-CAD")
else:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _SRC = os.path.join(_HERE, "payload", "ENCHANTER-CAD")
_APP = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                    "ENCHANTER-CAD 2D")
_EXE = os.path.join(_APP, "ENCHANTER-CAD.exe")
_ICON = os.path.join(_APP, "_internal", "assets", "icons", "appicon.ico")
_REG = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D"


class Worker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool)

    def run(self):
        try:
            import ctypes
            # copy payload
            self.log.emit("Copying files to %s ..." % _APP)
            if os.path.isdir(_APP):
                shutil.rmtree(_APP)
            shutil.copytree(_SRC, _APP)

            # shortcuts
            self.log.emit("Creating shortcuts ...")
            dt = os.path.join(os.environ.get("PUBLIC", os.path.expanduser("~")),
                              "Desktop", "ENCHANTER-CAD 2D.lnk")
            sm = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                              "Microsoft", "Windows", "Start Menu", "Programs",
                              "ENCHANTER-CAD 2D")
            try:
                import win32com.client  # optional
                _make_shortcut_win32(dt, _EXE, _APP, _ICON)
                os.makedirs(sm, exist_ok=True)
                _make_shortcut_win32(os.path.join(sm, "ENCHANTER-CAD 2D.lnk"),
                                     _EXE, _APP, _ICON)
            except Exception:
                _make_shortcut_ps(dt, _EXE, _APP, _ICON)
                os.makedirs(sm, exist_ok=True)
                _make_shortcut_ps(os.path.join(sm, "ENCHANTER-CAD 2D.lnk"),
                                  _EXE, _APP, _ICON)

            # registry
            self.log.emit("Registering with Control Panel ...")
            _reg_write(_REG, _APP, _EXE, _ICON)

            self.log.emit("Done. You can launch ENCHANTER-CAD 2D from the "
                          "Desktop or Start Menu.")
            self.done.emit(True)
        except Exception as e:
            self.log.emit("ERROR: %s" % e)
            self.done.emit(False)


def _make_shortcut_ps(path, target, work, icon):
    import subprocess
    ps = ('$ws=New-Object -ComObject WScript.Shell;'
          '$s=$ws.CreateShortcut(\'%s\');'
          '$s.TargetPath=\'%s\';$s.WorkingDirectory=\'%s\';'
          '$s.IconLocation=\'%s,0\';$s.Save()' % (path, target, work, icon))
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


def _make_shortcut_win32(path, target, work, icon):
    sh = win32com.client.Dispatch("WScript.Shell")
    sc = sh.CreateShortcut(path)
    sc.TargetPath = target
    sc.WorkingDirectory = work
    sc.IconLocation = "%s,0" % icon
    sc.Save()


def _reg_write(subkey, app, exe, icon):
    import winreg
    # remove any stale / misspelled entries from earlier builds
    parent = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    for stale in ("ENCHANTR-CAD2D", "ENCHANTER-CAD2D"):
        try:
            pk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, parent, 0,
                                winreg.KEY_SET_VALUE)
            winreg.DeleteKey(pk, stale)
            winreg.CloseKey(pk)
        except Exception:
            pass
    key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, subkey)
    winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "ENCHANTER-CAD 2D")
    winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "1.1")
    winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Enchantr")
    winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, app)
    winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, "%s,0" % icon)
    winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ,
                      '"%s" --uninstall' % exe)
    winreg.SetValueEx(key, "URLInfoAbout", 0, winreg.REG_SZ,
                      "https://sidharth-kr.pages.dev")
    winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
    winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    winreg.CloseKey(key)


class Installer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ENCHANTER-CAD 2D  -  Installer")
        self.setFixedSize(460, 380)
        self.setStyleSheet("QWidget{background:#0d1117;color:#e8eef5;}")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)

        title = QLabel("<b style='font-size:18px;color:#3a9bff;'>"
                       "ENCHANTER-CAD 2D</b><br>"
                       "<span style='color:#8b97a5;'>Version 1.1  -  Install</span>")
        root.addWidget(title)

        self.status = QLabel("This will install ENCHANTER-CAD 2D to:\n%s"
                             % _APP)
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:#c8d2dc;font:13px 'Segoe UI';")
        root.addWidget(self.status)

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(
            "QProgressBar{border:1px solid #2b3340;border-radius:7px;"
            "background:#161b22;}QProgressBar::chunk{background:#3a9bff;"
            "border-radius:6px;}")
        root.addWidget(self.bar)
        self.bar.hide()

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("QTextEdit{background:#161b22;border:1px solid "
                               "#2b3340;border-radius:8px;color:#9fb0bf;"
                               "font:11px 'Consolas';}")
        root.addWidget(self.log, 1)

        row = QHBoxLayout()
        self.install_btn = QPushButton("Install")
        self.install_btn.setStyleSheet(
            "QPushButton{background:#10261f;color:#00e5c0;border:1px solid "
            "#0c5a4b;border-radius:8px;padding:9px 20px;font:14px 'Segoe UI';}"
            "QPushButton:hover{background:#143a2e;}")
        self.install_btn.clicked.connect(self._install)
        row.addStretch(1)
        row.addWidget(self.install_btn)
        root.addLayout(row)

    def _install(self):
        if not os.path.isdir(_SRC):
            self.log.append("ERROR: portable build not found next to "
                            "installer (%s)." % _SRC)
            return
        self.install_btn.setEnabled(False)
        self.bar.show()
        self._worker = Worker()
        self._worker.log.connect(self.log.append)
        self._worker.done.connect(self._finished)
        self._worker.start()

    def _finished(self, ok):
        self.bar.hide()
        self.install_btn.setText("Close")
        self.install_btn.setEnabled(True)
        self.install_btn.clicked.disconnect()
        self.install_btn.clicked.connect(self.close)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Installer()
    w.show()
    sys.exit(app.exec())
