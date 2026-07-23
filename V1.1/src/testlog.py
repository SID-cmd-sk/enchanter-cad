"""
testlog.py
Lightweight debug/test log for PyCAD.

Records every command typed at the command line, when each command starts and
finishes, and any exception (with full traceback) that occurs while running a
command - so it is easy to see WHERE execution started, where it ended, and
where it failed/hung.

All entries are timestamped and appended to pycad_test_log.txt next to this
file. Call log(), log_start(), log_end(), log_error().
"""
import os
import time
import traceback

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pycad_test_log.txt")

_ENABLED = True


def enable(on=True):
    global _ENABLED
    _ENABLED = on


def _write(msg):
    if not _ENABLED:
        return
    try:
        ts = time.strftime("%H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def log(msg):
    _write(msg)


def log_start(cmd):
    _write(f">>> START command: {cmd}")


def log_end(cmd, result=""):
    _write(f"<<< END   command: {cmd}  ({result})")


def log_error(cmd, exc):
    _write(f"!!! ERROR in command: {cmd}")
    _write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))


def log_exception(context, exc):
    _write(f"!!! EXCEPTION [{context}]")
    _write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))


def separator():
    _write("-" * 60)
