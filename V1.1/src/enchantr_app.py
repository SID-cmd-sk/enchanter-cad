"""
enchantr_app.py
ENCHANTR-CAD 2D  --  application shell.

Adds the professional desktop experience around the core CAD window:
  * animated splash / loading screen ("Loading modules...")
  * branded welcome / start page (with portfolio link)
  * About dialog (portfolio link, version V1.1)
  * Post Manager entry (edit G-code post / location from the UI)

The core CAD window lives in main.py (MainWindow).  This module subclasses it
so the original engine code is preserved and only presentation/integration is
added.  Run with:  python enchantr_app.py
"""
import os
import sys
import time
import webbrowser

from PyQt6.QtWidgets import (QApplication, QSplashScreen, QMainWindow, QDialog,
                             QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
                             QProgressBar, QListWidget, QListWidgetItem,
                             QMessageBox, QTextBrowser, QFrame, QLineEdit)
from PyQt6.QtGui import QPixmap, QIcon, QFont, QColor, QPainter, QAction
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QRect, QSize

import license as lic

# ---- branding asset paths (resolve relative to this file) -------------
if getattr(sys, "frozen", False):
    # running from the PyInstaller bundle: assets shipped in _internal/assets
    _HERE = os.path.dirname(os.path.abspath(sys.executable))
    _ASSETS = os.path.join(_HERE, "_internal", "assets")
else:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _ASSETS = os.path.abspath(os.path.join(_HERE, "..", "assets"))
BRAND = os.path.join(_ASSETS, "branding")
ICONS = os.path.join(_ASSETS, "icons")
LOGO = os.path.join(BRAND, "logo.png")
SPLASH = os.path.join(BRAND, "splash.png")
STARTBG = os.path.join(_ASSETS, "startbg.png")

APP_NAME = "ENCHANTER-CAD 2D"
APP_VERSION = "1.1"
APP_PUBLISHER = "Enchantr"
PORTFOLIO_URL = "https://sidharth-kr.pages.dev"   # portfolio
SUPPORT_URL = "mailto:sidharthkr1859@gmail.com"
SUPPORT_EMAIL = "sidharthkr1859@gmail.com"

MODULES = [
    "Core engine", "Entity model", "Drawing canvas", "Command parser",
    "Ribbon & toolbar", "G-code generator", "Post-processors",
    "DXF I/O", "Constraints", "Dimensioning", "Text / fonts", "UI shell",
]


# =========================================================================
# Splash / loading screen
# =========================================================================
class SplashScreen(QSplashScreen):
    """Branded splash with a progress bar and 'Loading modules' text."""

    def __init__(self):
        pix = QPixmap(SPLASH)
        if pix.isNull():
            pix = QPixmap(900, 540)
            pix.fill(QColor("#0d1117"))
        super().__init__(pix, Qt.WindowType.WindowStaysOnTopHint)
        self.setMask(pix.mask() if not pix.mask().isNull() else QRect(0, 0, 900, 540))

        self._label = QLabel(self)
        self._label.setGeometry(0, 432, 900, 28)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color:#8b97a5; font:12px 'Segoe UI';")
        self._label.setText("Starting ENCHANTR-CAD 2D...")

        self._bar = QProgressBar(self)
        self._bar.setGeometry(280, 470, 340, 14)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(
            "QProgressBar{border:1px solid #2b3340; border-radius:7px;"
            "background:#161b22;}"
            "QProgressBar::chunk{background:#3a9bff; border-radius:6px;}")

    def set_status(self, text):
        self._label.setText(text)
        QApplication.processEvents()

    def set_progress(self, value):
        self._bar.setValue(value)
        QApplication.processEvents()


# =========================================================================
# Welcome / start page
# =========================================================================
class WelcomeDialog(QDialog):
    """Start menu shown after the splash.  Lets the user create/open a drawing
    or jump to documentation / portfolio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("%s  -  Start" % APP_NAME)
        self.setFixedSize(900, 560)
        self.setStyleSheet("QDialog{background:#0d1117;}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # header banner
        banner = QLabel()
        bpix = QPixmap(os.path.join(ICONS, "banner.png"))
        if not bpix.isNull():
            banner.setPixmap(bpix.scaledToWidth(900, Qt.TransformationMode.SmoothTransformation))
        root.addWidget(banner)

        body = QHBoxLayout()
        body.setContentsMargins(28, 20, 28, 20)
        root.addLayout(body)

        # left: action column
        left = QVBoxLayout()
        left.setSpacing(12)
        self._new_btn = QPushButton("  New Drawing")
        self._open_btn = QPushButton("  Open Drawing...")
        self._posts_btn = QPushButton("  Post Manager (G-code)")
        self._ref_btn = QPushButton("  Command Reference")
        self._about_btn = QPushButton("  About / Portfolio")
        for b in (self._new_btn, self._open_btn, self._posts_btn,
                  self._ref_btn, self._about_btn):
            b.setMinimumHeight(42)
            b.setStyleSheet(
                "QPushButton{background:#1b212b; color:#e8eef5; border:1px solid #2b3340;"
                "border-radius:8px; font:14px 'Segoe UI'; text-align:left; padding:0 14px;}"
                "QPushButton:hover{background:#222b38; border-color:#3a9bff;}"
                "QPushButton:pressed{background:#3a9bff; color:#0d1117;}")
            left.addWidget(b)
        self._new_btn.clicked.connect(lambda: self.done(1))
        self._open_btn.clicked.connect(lambda: self.done(2))
        self._posts_btn.clicked.connect(lambda: self.done(3))
        self._ref_btn.clicked.connect(lambda: self.done(4))
        self._about_btn.clicked.connect(lambda: self.done(5))
        left.addStretch(1)
        body.addLayout(left, 1)

        # right: info / portfolio
        right = QVBoxLayout()
        right.setContentsMargins(20, 0, 0, 0)
        info = QLabel()
        info.setWordWrap(True)
        info.setStyleSheet("color:#c8d2dc; font:13px 'Segoe UI';")
        info.setText(
            "<b style='color:#3a9bff;font-size:15px;'>Welcome to %s</b><br><br>"
            "A 2D CAD workspace with built-in CNC toolpath generation. "
            "Draw with the full A-Z command set, then post-process to your "
            "machine (Fanuc, Haas, GRBL, Mach3, LinuxCNC, and more).<br><br>"
            "Version <b>%s</b>" % (APP_NAME, APP_VERSION))
        right.addWidget(info)
        right.addSpacing(14)

        port = QPushButton("  Visit Portfolio  ↗")
        port.setMinimumHeight(40)
        port.setStyleSheet(
            "QPushButton{background:#10261f; color:#00e5c0; border:1px solid #0c5a4b;"
            "border-radius:8px; font:14px 'Segoe UI'; text-align:left; padding:0 14px;}"
            "QPushButton:hover{background:#143a2e;}")
        port.clicked.connect(lambda: webbrowser.open(PORTFOLIO_URL))
        right.addWidget(port)
        right.addStretch(1)
        body.addLayout(right, 1)

        # footer
        foot = QLabel("© %s %s   •   %s" % (APP_PUBLISHER, APP_VERSION, PORTFOLIO_URL))
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.setStyleSheet("color:#5b6675; font:11px 'Segoe UI'; padding:8px;")
        root.addWidget(foot)


# =========================================================================
# About dialog (portfolio link)
# =========================================================================
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About %s" % APP_NAME)
        self.setFixedSize(520, 360)
        self.setStyleSheet("QDialog{background:#0d1117;}")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)

        top = QHBoxLayout()
        logo = QLabel()
        lp = QPixmap(LOGO).scaled(84, 84, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
        logo.setPixmap(lp)
        top.addWidget(logo)
        txt = QLabel("<b style='color:#e8eef5;font-size:20px;'>%s</b><br>"
                     "<span style='color:#8b97a5;font-size:13px;'>Version %s<br>"
                     "2D CAD + CNC G-code workstation</span>" % (APP_NAME, APP_VERSION))
        top.addWidget(txt)
        top.addStretch(1)
        root.addLayout(top)

        root.addSpacing(16)
        body = QTextBrowser()
        body.setOpenExternalLinks(True)
        body.setStyleSheet("QTextBrowser{background:#161b22; border:1px solid #2b3340;"
                           "border-radius:8px; color:#c8d2dc; font:13px 'Segoe UI';}")
        body.setHtml(
            "<p>ENCHANTR-CAD 2D is a compact 2D CAD application with an integrated "
            "CAM post-processor pipeline.</p>"
            "<p><b>Publisher:</b> %s<br>"
            "<b>Version:</b> %s<br>"
            "<b>License:</b> 30-day free trial</p>"
            "<p><a href='%s' style='color:#3a9bff;'>Project portfolio &amp; docs ↗</a><br>"
            "<a href='%s' style='color:#00e5c0;'>Support: %s ↗</a></p>"
            % (APP_PUBLISHER, APP_VERSION, PORTFOLIO_URL, SUPPORT_URL, SUPPORT_EMAIL))
        root.addWidget(body, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.setMinimumWidth(110)
        close.setStyleSheet("QPushButton{background:#1b212b;color:#e8eef5;"
                             "border:1px solid #2b3340;border-radius:8px;padding:8px 14px;}"
                             "QPushButton:hover{background:#222b38;border-color:#3a9bff;}")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        root.addLayout(row)


# =========================================================================
# License / activation dialog (30-day trial)
# =========================================================================
class LicenseDialog(QDialog):
    """Shows trial status and lets the user enter the activation code."""

    def __init__(self, parent=None, expired=False):
        super().__init__(parent)
        self.setWindowTitle("Activate %s" % APP_NAME)
        self.setFixedSize(460, 340)
        self.setStyleSheet("QDialog{background:#0d1117;}")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)

        logo = QLabel()
        lp = QPixmap(LOGO).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
        logo.setPixmap(lp)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(logo)

        status = lic.license_status()
        if expired:
            head = "Trial expired"
            sub = ("Your 30-day free trial has ended. Enter your activation "
                   "code below to continue using %s." % APP_NAME)
        elif status[0] == "trial":
            head = "Free trial  -  %d days left" % status[1]
            sub = ("You are using the 30-day free trial of %s. Enter an "
                   "activation code any time to unlock it permanently."
                   % APP_NAME)
        else:
            head = "Product activated"
            sub = "%s is fully unlocked. Thank you!" % APP_NAME

        h = QLabel("<b style='color:#3a9bff;font-size:18px;'>%s</b>" % head)
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(h)
        s = QLabel(sub)
        s.setWordWrap(True)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setStyleSheet("color:#c8d2dc; font:13px 'Segoe UI';")
        root.addWidget(s)
        root.addSpacing(16)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Enter activation code")
        self.edit.setStyleSheet(
            "QLineEdit{background:#161b22; color:#e8eef5; border:1px solid #2b3340;"
            "border-radius:8px; font:14px 'Segoe UI'; padding:8px 12px;}"
            "QLineEdit:focus{border-color:#3a9bff;}")
        root.addWidget(self.edit)

        self.msg = QLabel("")
        self.msg.setStyleSheet("color:#ff6b6b; font:12px 'Segoe UI';")
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.msg)

        row = QHBoxLayout()
        row.addStretch(1)
        if status[0] != "activated":
            act = QPushButton("Activate")
            act.setStyleSheet(
                "QPushButton{background:#1b212b;color:#e8eef5;"
                "border:1px solid #2b3340;border-radius:8px;padding:8px 18px;}"
                "QPushButton:hover{background:#222b38;border-color:#3a9bff;}")
            act.clicked.connect(self._activate)
            row.addWidget(act)
        cont = QPushButton("Continue" if status[0] != "activated" else "Close")
        cont.setStyleSheet(
            "QPushButton{background:#10261f;color:#00e5c0;"
            "border:1px solid #0c5a4b;border-radius:8px;padding:8px 18px;}"
            "QPushButton:hover{background:#143a2e;}")
        cont.clicked.connect(self.accept)
        row.addWidget(cont)
        root.addLayout(row)

    def _activate(self):
        if lic.activate(self.edit.text()):
            QMessageBox.information(self, "Activated",
                                    "%s is now fully unlocked." % APP_NAME)
            self.accept()
        else:
            self.msg.setText("Invalid activation code.")


# =========================================================================
# Post Manager  (modify post / location from the UI)
# =========================================================================
class PostManagerDialog(QDialog):
    """Lets the user pick a machine post and tune its variables / options,
    then SAVE it back as a .py file in posts/ (the post *location*).  This is
    the dedicated top-level place to modify posts without opening the G-code
    dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Post Manager  -  G-code Posts")
        self.resize(640, 520)
        self.setStyleSheet("QDialog{background:#0d1117;}")
        import posts as gp
        self.pm = gp.PostManager()
        posts = self.pm.list_posts()
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Machine post:"))
        self.combo = QListWidget()
        for p in posts:
            self.combo.addItem(p.name)
        if posts:
            self.combo.setCurrentRow(0)
        self.combo.currentRowChanged.connect(self._load)
        top.addWidget(self.combo, 1)
        root.addLayout(top)

        self.form = QVBoxLayout()
        root.addLayout(self.form)

        bar = QHBoxLayout()
        save = QPushButton("Save Post (.py)")
        save.setStyleSheet("QPushButton{background:#1b212b;color:#e8eef5;"
                           "border:1px solid #2b3340;border-radius:8px;padding:8px 14px;}"
                           "QPushButton:hover{background:#222b38;border-color:#3a9bff;}")
        save.clicked.connect(self._save)
        bar.addStretch(1)
        bar.addWidget(save)
        root.addLayout(bar)

        self._post = posts[0] if posts else None
        self._load()

    def _load(self):
        # clear form
        while self.form.count():
            w = self.form.takeAt(0).widget()
            if w:
                w.deleteLater()
        if self._post is None:
            self.form.addWidget(QLabel("No posts found in posts/."))
            return
        self._post = self.pm.get_post(self.combo.currentItem().text())
        self._vars = {}
        self._opts = {}
        self.form.addWidget(QLabel("<b style='color:#3a9bff;'>Variables</b> "
                                    "(named values used in templates as {var:NAME})"))
        from PyQt6.QtWidgets import QLineEdit, QCheckBox, QFormLayout
        vf = QFormLayout()
        for k, val in getattr(self._post, "variables", {}).items():
            le = QLineEdit(str(val))
            self._vars[k] = le
            vf.addRow(k, le)
        self.form.addLayout(vf)

        self.form.addWidget(QLabel("<b style='color:#3a9bff;'>Options</b> "
                                    "(processor toggles)"))
        for k, val in getattr(self._post, "options", {}).items():
            cb = QCheckBox(k)
            cb.setChecked(bool(val))
            self._opts[k] = cb
            self.form.addWidget(cb)
        self.form.addStretch(1)

    def _save(self):
        if self._post is None:
            return
        data = {
            "name": self._post.name,
            "description": getattr(self._post, "description", ""),
            "options": {k: cb.isChecked() for k, cb in self._opts.items()},
            "variables": {k: float(le.text() or 0.0) for k, le in self._vars.items()},
        }
        from posts import Post
        new_post = Post(data)
        # preserve existing templates
        new_post.templates = dict(getattr(self._post, "templates", {}))
        path = new_post.save_to_folder(self.pm.posts_dir)
        QMessageBox.information(self, "Saved", "Post saved to:\n%s" % path)


# =========================================================================
# Branded main window
# =========================================================================
def _build_branded_window():
    """Import the core CAD window and return a decorated instance."""
    import main as core
    import command_table

    win = core.MainWindow()
    win.setWindowTitle("%s  V%s" % (APP_NAME, APP_VERSION))
    try:
        win.setWindowIcon(QIcon(LOGO))
    except Exception:
        pass

    # add a Post Manager + About entry to the Tools / Help menus
    menubar = win.menuBar()

    tools = None
    helpm = None
    for act in menubar.actions():
        if act.text().replace("&", "") == "Tools":
            tools = act.menu()
        if act.text().replace("&", "") == "Help":
            helpm = act.menu()

    if tools is None:
        tools = menubar.addMenu("&Tools")
    if helpm is None:
        helpm = menubar.addMenu("&Help")

    pm_act = QAction("Post Manager (G-code)...", win)
    pm_act.triggered.connect(lambda: PostManagerDialog(win).exec())
    tools.addAction(pm_act)

    about_act = QAction("About %s" % APP_NAME, win)
    about_act.triggered.connect(lambda: AboutDialog(win).exec())
    helpm.addAction(about_act)

    # keep a reference so it isn't GC'd
    win._enchantr_about = about_act
    win._enchantr_pm = pm_act
    return win


# =========================================================================
# Uninstall support (Control Panel "Uninstall" button)
# =========================================================================
def _is_admin():
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _uninstall():
    """Remove install dir, shortcuts and registry entry.

    Deleting C:\\Program Files + HKLM requires admin.  If we are not already
    elevated we relaunch this exe with 'runas' so Windows shows the UAC
    prompt, then exit.  The elevated copy performs the actual removal."""
    import shutil
    import ctypes
    import subprocess

    if not _is_admin():
        # relaunch elevated and let this instance exit
        exe = sys.executable
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe, "--uninstall", None, 1)
        except Exception:
            ctypes.windll.user32.MessageBoxW(
                0, "Please run uninstall as Administrator.",
                "ENCHANTER-CAD 2D", 0)
        sys.exit(0)

    app_dir = os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"),
                           "ENCHANTER-CAD 2D")
    dt = os.path.join(os.environ.get("PUBLIC", os.path.expanduser("~")),
                      "Desktop", "ENCHANTER-CAD 2D.lnk")
    sm = os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"),
                      "Microsoft", "Windows", "Start Menu", "Programs",
                      "ENCHANTER-CAD 2D")
    errors = []
    for p in (dt,):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception as e:
            errors.append(str(e))
    for d in (app_dir, sm):
        try:
            if os.path.isdir(d):
                shutil.rmtree(d)
        except Exception as e:
            errors.append(str(e))
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
                             0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteKey(key, "ENCHANTER-CAD2D")
        except Exception:
            pass
        winreg.CloseKey(key)
    except Exception as e:
        errors.append(str(e))

    msg = "ENCHANTER-CAD 2D has been uninstalled." if not errors \
        else ("Uninstall partially completed:\n" + "\n".join(errors))
    try:
        ctypes.windll.user32.MessageBoxW(0, msg, "ENCHANTER-CAD 2D", 0)
    except Exception:
        print(msg)
    sys.exit(0)


# =========================================================================
# Boot sequence: splash -> (optional welcome) -> main window
# =========================================================================
def run():
    if "--uninstall" in sys.argv:
        _uninstall()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # ---- license / trial gate -----------------------------------------
    status = lic.license_status()
    if status[0] != "activated":
        dlg = LicenseDialog(expired=(status[0] == "expired"))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
        # re-check after activation attempt
        if lic.license_status()[0] == "expired" and not lic.is_activated():
            sys.exit(0)

    p = os.path.join(_HERE, "main.py")
    # reuse the core stylesheet by importing it after QApplication exists
    import main as core
    app.setStyleSheet(core.APP_STYLESHEET)
    try:
        app.setWindowIcon(QIcon(LOGO))
    except Exception:
        pass

    splash = SplashScreen()
    splash.show()
    app.processEvents()

    # animated module load
    n = len(MODULES)
    for i, name in enumerate(MODULES):
        splash.set_status("Loading %s ..." % name)
        splash.set_progress(int((i + 1) / n * 100))
        time.sleep(0.06)
    splash.set_status("Application ready.")
    splash.set_progress(100)
    app.processEvents()
    time.sleep(0.25)

    win = _build_branded_window()

    # welcome / start page (skippable)
    welcome = WelcomeDialog()
    splash.finish(win)
    win.show()
    win.cmdline.setFocus()
    app.installEventFilter(win)

    code = welcome.exec()
    if code == 1:
        win.new_drawing()
    elif code == 2:
        win.open_drawing()
    elif code == 3:
        PostManagerDialog(win).exec()
    elif code == 4:
        win.show_command_reference()
    elif code == 5:
        AboutDialog(win).exec()

    sys.exit(app.exec())


if __name__ == "__main__":
    run()
