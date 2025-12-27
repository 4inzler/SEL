"""
Tmux Control API for SEL Bot

Provides persistent terminal session control via tmux, allowing:
- Multiple named sessions
- Command execution with output capture
- Interactive workflows
- Session state management
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional

HOST = "0.0.0.0"
PORT = 9001  # Different from host_exec (9000)
TMUX_TOKEN = os.environ.get("TMUX_CONTROL_TOKEN")
HOME_DIR = os.path.expanduser("~")  # User's home directory

# Session management
SESSIONS: Dict[str, dict] = {}
DEFAULT_SESSION = "sel-main"


def _run_tmux(args: List[str], capture: bool = True) -> tuple[int, str, str]:
    """Run tmux command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["tmux"] + args,
            capture_output=capture,
            text=True,
            timeout=10,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as exc:
        return -1, "", str(exc)


def _ensure_session(session_name: str = DEFAULT_SESSION) -> bool:
    """Ensure tmux session exists, create if needed."""
    # Check if session exists
    code, stdout, _ = _run_tmux(["has-session", "-t", session_name])
    if code == 0:
        return True

    # Create new session (detached) starting in home directory
    code, _, stderr = _run_tmux(["new-session", "-d", "-s", session_name, "-c", HOME_DIR])
    if code == 0:
        SESSIONS[session_name] = {
            "created_at": time.time(),
            "command_count": 0,
            "last_command_at": None,
        }
        return True

    return False


def _send_command(session_name: str, command: str) -> bool:
    """Send command to tmux session."""
    if not _ensure_session(session_name):
        return False

    # Send keys to session
    code, _, _ = _run_tmux([
        "send-keys",
        "-t",
        session_name,
        command,
        "Enter"
    ])

    if code == 0 and session_name in SESSIONS:
        SESSIONS[session_name]["command_count"] += 1
        SESSIONS[session_name]["last_command_at"] = time.time()

    return code == 0


def _capture_output(session_name: str, lines: int = 100) -> str:
    """Capture recent output from tmux pane."""
    if not _ensure_session(session_name):
        return ""

    code, stdout, _ = _run_tmux([
        "capture-pane",
        "-t",
        session_name,
        "-p",  # Print to stdout
        "-S",  # Start line
        f"-{lines}",
    ])

    return stdout if code == 0 else ""


def _list_sessions() -> List[dict]:
    """List all tmux sessions."""
    code, stdout, _ = _run_tmux(["list-sessions", "-F", "#{session_name}"])
    if code != 0:
        return []

    sessions = []
    for line in stdout.strip().split("\n"):
        session_name = line.strip()
        if session_name:
            info = SESSIONS.get(session_name, {})
            sessions.append({
                "name": session_name,
                "created_at": info.get("created_at"),
                "command_count": info.get("command_count", 0),
                "last_command_at": info.get("last_command_at"),
            })

    return sessions


def _kill_session(session_name: str) -> bool:
    """Kill a tmux session."""
    code, _, _ = _run_tmux(["kill-session", "-t", session_name])
    if code == 0 and session_name in SESSIONS:
        del SESSIONS[session_name]
    return code == 0


class TmuxHandler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _check_auth(self) -> bool:
        # Token is optional for local development
        if TMUX_TOKEN:
            token = self.headers.get("X-Tmux-Token")
            if token != TMUX_TOKEN:
                self._send_json(401, {"detail": "Unauthorized"})
                return False
        return True

    def do_POST(self):  # noqa: N802
        if not self._check_auth():
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._send_json(400, {"detail": "Invalid JSON"})
            return

        # Route to appropriate handler
        if self.path == "/sessions":
            self._handle_create_session(data)
        elif self.path == "/execute":
            self._handle_execute(data)
        elif self.path == "/capture":
            self._handle_capture(data)
        else:
            self._send_json(404, {"detail": "Not found"})

    def do_GET(self):  # noqa: N802
        if not self._check_auth():
            return

        if self.path == "/sessions":
            sessions = _list_sessions()
            self._send_json(200, {"sessions": sessions})
        elif self.path.startswith("/sessions/"):
            session_name = self.path.split("/")[-1]
            output = _capture_output(session_name)
            self._send_json(200, {
                "session": session_name,
                "output": output,
            })
        else:
            self._send_json(404, {"detail": "Not found"})

    def do_DELETE(self):  # noqa: N802
        if not self._check_auth():
            return

        if self.path.startswith("/sessions/"):
            session_name = self.path.split("/")[-1]
            success = _kill_session(session_name)
            if success:
                self._send_json(200, {"status": "killed", "session": session_name})
            else:
                self._send_json(404, {"detail": "Session not found"})
        else:
            self._send_json(404, {"detail": "Not found"})

    def _handle_create_session(self, data: dict):
        """Create a new tmux session."""
        session_name = data.get("session_name", DEFAULT_SESSION)
        if _ensure_session(session_name):
            self._send_json(201, {
                "status": "created",
                "session": session_name,
            })
        else:
            self._send_json(500, {"detail": "Failed to create session"})

    def _handle_execute(self, data: dict):
        """Execute command in tmux session."""
        command = data.get("command", "").strip()
        session_name = data.get("session", DEFAULT_SESSION)
        capture_output = data.get("capture_output", True)
        wait_ms = data.get("wait_ms", 1000)  # Wait for output
        ephemeral = data.get("ephemeral", True)  # Default to ephemeral sessions

        if not command:
            self._send_json(400, {"detail": "Empty command"})
            return

        # Send command
        if not _send_command(session_name, command):
            self._send_json(500, {"detail": "Failed to send command"})
            return

        # Wait for command to execute
        time.sleep(wait_ms / 1000.0)

        # Capture output if requested
        output = ""
        if capture_output:
            output = _capture_output(session_name)

        # Kill session after command if ephemeral
        if ephemeral:
            _kill_session(session_name)

        self._send_json(200, {
            "status": "executed",
            "session": session_name,
            "command": command,
            "output": output,
            "ephemeral": ephemeral,
        })

    def _handle_capture(self, data: dict):
        """Capture output from session."""
        session_name = data.get("session", DEFAULT_SESSION)
        lines = data.get("lines", 100)

        output = _capture_output(session_name, lines)
        self._send_json(200, {
            "session": session_name,
            "output": output,
        })


def main():
    # Ensure tmux is installed
    code, _, _ = _run_tmux(["list-sessions"])
    if code == -1:
        print("ERROR: tmux is not installed or not in PATH")
        return

    server = HTTPServer((HOST, PORT), TmuxHandler)
    print(f"Tmux Control API listening on http://{HOST}:{PORT}")
    print("Available endpoints:")
    print("  POST   /sessions        - Create new session")
    print("  GET    /sessions        - List all sessions")
    print("  GET    /sessions/{name} - Get session output")
    print("  DELETE /sessions/{name} - Kill session")
    print("  POST   /execute         - Execute command")
    print("  POST   /capture         - Capture output")
    server.serve_forever()


if __name__ == "__main__":
    main()
