"""Thin Python client for the Open CAD Studio headless automation server.

Launches `OpenCADStudio --serve` and talks to it over a line-based JSON protocol
(one request object per line on stdin, one response per line on stdout). There
is nothing to compile or maintain on the Python side — every method is one JSON
message; the real work is Open CAD Studio's own command system.

    from ocs import Ocs

    with Ocs(binary="OpenCADStudio") as ocs:
        ocs.open("plan.dwg")
        ocs.run("LAYER Walls")
        print(ocs.entities())          # {"total": 42, "by_type": {...}}
        ocs.save("plan_out.dwg")

Each call returns the parsed response dict and raises `OcsError` on `ok: false`.
"""

from __future__ import annotations

import json
import socket
import subprocess
from typing import Any, Optional


class OcsError(RuntimeError):
    """Raised when the server replies with `{"ok": false, ...}`."""


class Ocs:
    """Connect by spawning the server (default) or over a TCP socket.

    - `Ocs()` spawns `OpenCADStudio --serve` and talks over stdin/stdout.
    - `Ocs(port=4242)` connects to a server started with `--serve --port 4242`.
    """

    def __init__(
        self,
        binary: str = "OpenCADStudio",
        port: Optional[int] = None,
        host: str = "127.0.0.1",
    ) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.sock: Optional[socket.socket] = None
        if port is not None:
            self.sock = socket.create_connection((host, port))
            io = self.sock.makefile("rw")
            self._r, self._w = io, io
        else:
            self.proc = subprocess.Popen(
                [binary, "--serve"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self._r, self._w = self.proc.stdout, self.proc.stdin
        self._read()  # the {"ready": true} greeting

    # ── protocol ────────────────────────────────────────────────────────────
    def _read(self) -> dict[str, Any]:
        line = self._r.readline()
        if not line:
            raise OcsError("server closed the connection")
        return json.loads(line)

    def _send(self, **req: Any) -> dict[str, Any]:
        self._w.write(json.dumps(req) + "\n")
        self._w.flush()
        resp = self._read()
        if not resp.get("ok", False):
            raise OcsError(resp.get("error", "unknown error"))
        return resp

    # ── operations ──────────────────────────────────────────────────────────
    def new(self) -> dict[str, Any]:
        """Start an empty document."""
        return self._send(op="new")

    def open(self, path: str) -> dict[str, Any]:
        """Load a DWG/DXF drawing."""
        return self._send(op="open", path=path)

    def run(self, cmd: str) -> dict[str, Any]:
        """Run a command through Open CAD Studio's command system."""
        return self._send(op="run", cmd=cmd)

    def entities(self) -> dict[str, Any]:
        """Total entity count and a breakdown by type."""
        return self._send(op="entities")

    def query(
        self,
        type: Optional[str] = None,
        layer: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """List entities (handle, type, layer, geometry), optionally filtered."""
        return self._send(op="query", type=type, layer=layer, limit=limit)

    def layers(self) -> dict[str, Any]:
        """List layers (name, color, on/off, frozen, locked) and the current one."""
        return self._send(op="layers")

    def header(self) -> dict[str, Any]:
        """Read drawing header variables (units, PDMODE/PDSIZE, LTSCALE, …)."""
        return self._send(op="header")

    def select(
        self,
        handles: Optional[list[str]] = None,
        type: Optional[str] = None,
        layer: Optional[str] = None,
        clear: bool = False,
    ) -> dict[str, Any]:
        """Set the selection by handle, type, or layer (a following selection
        command like ``run("ERASE")`` then acts on it). `clear=True` deselects."""
        return self._send(
            op="select", handles=handles, type=type, layer=layer, clear=clear
        )

    def undo(self) -> dict[str, Any]:
        """Undo the last change."""
        return self._send(op="undo")

    def redo(self) -> dict[str, Any]:
        """Redo the last undone change."""
        return self._send(op="redo")

    def save(self, path: Optional[str] = None) -> dict[str, Any]:
        """Write the document (defaults to the opened/last-saved path)."""
        return self._send(op="save", path=path)

    # ── lifecycle ───────────────────────────────────────────────────────────
    def close(self) -> None:
        try:
            self._w.close()
        except Exception:
            pass
        if self.proc is not None:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.sock is not None:
            self.sock.close()

    def __enter__(self) -> "Ocs":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
