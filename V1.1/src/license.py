"""
license.py
ENCHANTR-CAD 2D  --  simple trial / activation handling.

* 30-day free trial based on first-run timestamp (stored in config/license.ini)
* One-time activation with the code "Tanu19" unlocks the product permanently.

This is a lightweight client-side gate (not a secure DRM system).
"""
import os
import sys
import time

from PyQt6.QtCore import QSettings

# Always store the license in the user's AppData (writable without admin).
# This makes activation persist across runs and across reinstalls for that user.
_CONFIG_ROOT = os.path.join(
    os.environ.get("LOCALAPPDATA")
    or os.environ.get("APPDATA")
    or os.path.expanduser("~"),
    "ENCHANTER-CAD 2D",
)
CONFIG_DIR = _CONFIG_ROOT
LICENSE_PATH = os.path.join(CONFIG_DIR, "license.ini")

os.makedirs(CONFIG_DIR, exist_ok=True)

APP_NAME = "ENCHANTR-CAD 2D"
TRIAL_DAYS = 30
ACTIVATION_CODE = "Tanu19"

_SETTINGS = QSettings(LICENSE_PATH, QSettings.Format.IniFormat)


def _first_run_timestamp():
    ts = _SETTINGS.value("trial/first_run", None)
    if ts is None:
        ts = str(int(time.time()))
        _SETTINGS.setValue("trial/first_run", ts)
        _SETTINGS.sync()
    return int(float(ts))


def is_activated():
    return _SETTINGS.value("license/activated", "false") == "true"


def activate(code):
    if code.strip() == ACTIVATION_CODE:
        _SETTINGS.setValue("license/activated", "true")
        _SETTINGS.sync()
        return True
    return False


def trial_remaining_days():
    """Return (days_remaining, expired)."""
    elapsed = (int(time.time()) - _first_run_timestamp()) / 86400.0
    remaining = int(TRIAL_DAYS - elapsed)
    return max(remaining, 0), remaining <= 0


def license_status():
    """('activated' | 'trial' | 'expired', days_remaining)."""
    if is_activated():
        return "activated", 0
    remaining, expired = trial_remaining_days()
    return ("expired" if expired else "trial"), remaining
