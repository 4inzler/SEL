"""Minimal host-side HTTP API (stdlib only) to run whitelisted commands for Sel."""

from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer


HOST = "0.0.0.0"
PORT = 9000
HOST_TOKEN = os.environ.get("HOST_EXEC_TOKEN")
HOME_DIR = os.path.expanduser("~")  # User's home directory
DEFAULT_WHITELIST = ["*"]
WHITELIST = [
    cmd.strip()
    for cmd in os.environ.get("HOST_EXEC_WHITELIST", ",".join(DEFAULT_WHITELIST)).split(",")
    if cmd.strip()
]


def _allowed(cmd: str) -> bool:
    if "*" in WHITELIST:
        return True
    return any(cmd.strip().startswith(item) for item in WHITELIST)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):  # noqa: N802
        if self.path != "/run":
            self._send(404, {"detail": "Not found"})
            return

        # Token is optional for local development
        if HOST_TOKEN:
            token = self.headers.get("X-Exec-Token")
            if token != HOST_TOKEN:
                self._send(401, {"detail": "Unauthorized"})
                return
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._send(400, {"detail": "Invalid JSON"})
            return
        cmd = str(data.get("command") or "").strip()
        if not cmd:
            self._send(400, {"detail": "Empty command"})
        if not _allowed(cmd):
            self._send(403, {"detail": "Command not allowed"})
            return
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=HOME_DIR  # Execute in home directory
            )
            self._send(
                200,
                {
                    "command": cmd,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                },
            )
        except subprocess.TimeoutExpired:
            self._send(504, {"detail": "Command timed out"})
        except Exception as exc:
            self._send(500, {"detail": f"Command failed: {exc}"})


def main():
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Host exec API listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
