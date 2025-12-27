"""
System Agent for SEL - Autonomous System Companion

Sel's interface to the underlying system. Not a tool to be invoked,
but capabilities Sel uses naturally when the conversation calls for it.

Design philosophy:
- Conversational, not command-driven
- Sel responds like a friend who happens to have shell access
- Natural language understanding via LLM, not rigid patterns
- Proactive and curious, not just reactive

This agent should feel invisible - users talk to Sel naturally,
and Sel figures out when to use system capabilities.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import subprocess
import pathlib

DESCRIPTION = "Sel's system access - talk naturally about files, processes, services, or anything on the system."

# API Configuration
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_UTIL_MODEL = os.environ.get("OPENROUTER_UTIL_MODEL", "anthropic/claude-3-haiku-20240307")

# Sel's home base
HOME = os.path.expanduser("~")
SEL_HOME = "/home/ayla/Documents/Coding/SEL"
LOG_DIR = pathlib.Path("/tmp/sel_agent_jobs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class CommandResult:
    """Result of a command execution."""
    success: bool
    output: str
    error_hint: Optional[str] = None


@dataclass
class SystemState:
    """Sel's awareness of the system."""
    cwd: str = field(default_factory=lambda: HOME)
    last_output: str = ""
    last_command: str = ""
    history: List[str] = field(default_factory=list)
    jobs: Dict[str, Dict[str, str]] = field(default_factory=dict)  # name -> {"pid": str, "log": str}

    def remember(self, cmd: str):
        self.history.append(cmd)
        if len(self.history) > 30:
            self.history = self.history[-30:]


# Persistent state
_state = SystemState()


# ============================================================================
# Core Execution
# ============================================================================

def _llm_understand(query: str) -> Dict[str, Any]:
    """
    Use LLM to understand what the user wants.
    Returns: {"action": str, "params": dict, "command": str or None}

    Actions: navigate, location, system_health, disk, memory, processes,
             port, service, docker, git, network, files, read_file,
             large_files, jobs, history, help, run_command
    """
    if not OPENROUTER_API_KEY:
        # Fallback if no API key - try to extract obvious commands
        return {"action": "run_command", "params": {}, "command": query}

    prompt = f"""You are parsing a system query. The user is at: {_state.cwd}

Analyze this query and respond with JSON only:
{{"action": "<action>", "params": {{}}, "command": "<shell command if action is run_command, else null>"}}

Actions:
- navigate: user wants to go somewhere. params: {{"path": "<path>"}}
- location: user asks where they are
- system_health: general system status check
- disk: disk space query
- memory: RAM/memory query
- processes: what's running, optionally filtered. params: {{"filter": "<optional filter>"}}
- port: check what's on a port. params: {{"port": "<port number>"}}
- service: check a systemd service. params: {{"name": "<service name>"}}
- docker: docker/container status or action. params: {{"action": "status|restart|logs", "container": "<name if specific>"}}
- git: git status or operations
- network: network info, IPs, interfaces
- files: list files in a directory. params: {{"path": "<path or . for current>"}}
- read_file: show contents of a file. params: {{"path": "<file path>"}}
- large_files: find large files. params: {{"path": "<search path>"}}
- weather: weather query (current conditions, forecast, rain check). params: {{"type": "current|forecast|rain"}}
- jobs: background job management
- history: show command history
- help: user needs help
- run_command: run a specific shell command. params: {{}}, command: "<the command>"

Query: {query}

Respond with valid JSON only, no markdown:"""

    try:
        import httpx  # Lazy import so agent loads without optional deps
    except ImportError:
        return {"action": "run_command", "params": {}, "command": query}

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENROUTER_UTIL_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 200,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            # Parse JSON, handling potential markdown wrapping
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
    except Exception as e:
        # Fallback on error
        return {"action": "run_command", "params": {}, "command": query}


def _run(cmd: str, wait_ms: int = 2000, background: bool = False) -> CommandResult:
    """Run a command locally inside the container."""
    _state.last_command = cmd.strip()

    # Adjust wait time for heavier commands
    if any(x in cmd for x in ["npm install", "pip install", "cargo build", "docker build"]):
        wait_ms = max(wait_ms, 30000)
    elif any(x in cmd for x in ["git clone", "wget", "curl -O", "docker pull"]):
        wait_ms = max(wait_ms, 15000)

    full_cmd = f"cd {_state.cwd} && {cmd}"

    if background:
        try:
            log_path = LOG_DIR / f"job-{int(time.time()*1000)}.log"
            with open(log_path, "w") as log_file:
                proc = subprocess.Popen(
                    full_cmd,
                    shell=True,
                    cwd=_state.cwd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            job_name = f"job-{proc.pid}"
            _state.jobs[job_name] = {"pid": str(proc.pid), "log": str(log_path)}
            return CommandResult(True, f"started in background ({job_name})")
        except Exception as exc:
            return CommandResult(False, str(exc), "could not start background job")

    try:
        completed = subprocess.run(
            full_cmd,
            shell=True,
            cwd=_state.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=max(1, wait_ms / 1000),
        )
        output = (completed.stdout or "").strip()
    except subprocess.TimeoutExpired as exc:
        return CommandResult(False, exc.stdout or "", "timed out")
    except Exception as exc:
        return CommandResult(False, str(exc), "failed to run")

    _state.last_output = output
    _state.remember(cmd)

    hint = None
    output_lower = output.lower()
    if "permission denied" in output_lower:
        hint = "might need sudo for that"
    elif "command not found" in output_lower:
        hint = "that command isn't installed"
    elif "no such file" in output_lower:
        hint = "path doesn't exist"
    elif "connection refused" in output_lower:
        hint = "nothing listening there"
    elif "address already in use" in output_lower:
        hint = "port's already taken"

    success = hint is None and completed.returncode == 0
    return CommandResult(success, output, hint)


def _go(path: str) -> str:
    """Change where Sel is looking."""
    # Understand common references
    shortcuts = {
        "home": HOME,
        "~": HOME,
        "sel": SEL_HOME,
        "here": SEL_HOME,
        "tmp": "/tmp",
        "downloads": f"{HOME}/Downloads",
        "projects": f"{HOME}/Documents/Coding",
    }

    if path.lower() in shortcuts:
        path = shortcuts[path.lower()]
    elif path == "..":
        path = os.path.dirname(_state.cwd)
    elif not path.startswith("/"):
        path = os.path.join(_state.cwd, path)

    # Check it exists
    result = _run(f"cd {path} && pwd", wait_ms=500)
    if result.success and result.output:
        _state.cwd = result.output.split("\n")[-1].strip()

        # Take a look around
        ls = _run("ls -la | head -12", wait_ms=500)

        return f"moved to `{_state.cwd}`\n```\n{ls.output}\n```"
    else:
        return f"can't get to `{path}` - {result.error_hint or 'not found'}"


# ============================================================================
# Understanding Intent (LLM-based)
# ============================================================================

def _understand(query: str) -> str:
    """Use LLM to understand what the user wants, then do it."""

    # Ask the LLM what the user wants
    intent = _llm_understand(query)
    action = intent.get("action", "run_command")
    params = intent.get("params", {})
    command = intent.get("command")

    # Route to the appropriate handler
    if action == "navigate":
        path = params.get("path", "")
        if path:
            return _go(path)
        return f"we're in `{_state.cwd}`"

    elif action == "location":
        return f"we're in `{_state.cwd}`"

    elif action == "system_health":
        return _check_system()

    elif action == "disk":
        r = _run("df -h / /home 2>/dev/null | tail -n+2")
        return f"disk usage:\n```\n{r.output}\n```"

    elif action == "memory":
        r = _run("free -h")
        return f"memory:\n```\n{r.output}\n```"

    elif action == "processes":
        filt = params.get("filter")
        if filt:
            r = _run(f"ps aux | head -1; ps aux | grep -i {filt} | grep -v grep")
        else:
            r = _run("ps aux --sort=-%mem | head -12")
        return f"```\n{r.output}\n```"

    elif action == "port":
        port = params.get("port", "")
        if port:
            r = _run(f"lsof -i :{port} 2>/dev/null || ss -tlnp 2>/dev/null | grep :{port}")
            if r.output.strip():
                return f"port {port}:\n```\n{r.output}\n```"
            return f"nothing on port {port}"
        r = _run("ss -tlnp 2>/dev/null | head -15")
        return f"listening:\n```\n{r.output}\n```"

    elif action == "service":
        svc = params.get("name", "")
        if svc:
            r = _run(f"systemctl status {svc} --no-pager 2>/dev/null | head -12")
            if "could not be found" in r.output.lower():
                return f"no service called `{svc}`"
            return f"```\n{r.output}\n```"
        return "which service?"

    elif action == "docker":
        docker_action = params.get("action", "status")
        container = params.get("container")

        if docker_action == "restart" and container:
            r = _run(f"docker restart {container}", wait_ms=10000)
            if r.success:
                logs = _run(f"docker logs --tail 10 {container} 2>&1", wait_ms=2000)
                return f"restarted `{container}`\n```\n{logs.output}\n```"
            return f"couldn't restart `{container}`: {r.output}"

        elif docker_action == "logs" and container:
            r = _run(f"docker logs --tail 30 {container} 2>&1", wait_ms=2000)
            return f"```\n{r.output}\n```"

        else:  # status
            r = _run("docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null")
            if "Cannot connect" in r.output:
                return "docker daemon isn't running"
            if not r.output.strip() or "NAMES" not in r.output:
                return "no containers running"
            return f"```\n{r.output}\n```"

    elif action == "git":
        return _check_git()

    elif action == "network":
        r = _run("ip -4 addr show | grep inet | grep -v 127.0.0.1")
        return f"network:\n```\n{r.output}\n```"

    elif action == "files":
        path = params.get("path", ".")
        r = _run(f"ls -la {path} | head -20")
        return f"```\n{r.output}\n```"

    elif action == "read_file":
        path = params.get("path", "")
        if path:
            r = _run(f"cat {path} 2>/dev/null | head -50")
            if r.output:
                return f"```\n{r.output}\n```"
            return f"can't read `{path}`"
        return "which file?"

    elif action == "large_files":
        path = params.get("path", ".")
        r = _run(f"find {path} -type f -size +50M -exec ls -lh {{}} \\; 2>/dev/null | sort -k5 -h | tail -10", wait_ms=10000)
        if r.output.strip():
            return f"large files:\n```\n{r.output}\n```"
        return f"nothing over 50MB in `{path}`"

    elif action == "weather":
        # Delegate to weather agent
        try:
            from agents import weather
            weather_type = params.get("type", "current")
            return weather.run(weather_type)
        except Exception as e:
            return f"couldn't get weather: {e}"

    elif action == "jobs":
        return _list_jobs()

    elif action == "history":
        if not _state.history:
            return "haven't run anything yet"
        cmds = "\n".join(_state.history[-10:])
        return f"recent:\n```\n{cmds}\n```"

    elif action == "help":
        return _show_help()

    elif action == "run_command":
        # LLM determined this is a direct command to run
        cmd = command or query
        result = _run(cmd)

        if result.success:
            if result.output:
                lines = result.output.split("\n")
                if len(lines) > 35:
                    output = "\n".join(lines[-35:])
                    return f"```\n...({len(lines)-35} lines above)\n{output}\n```"
                return f"```\n{result.output}\n```"
            return "done (no output)"
        else:
            msg = "that didn't work"
            if result.error_hint:
                msg += f" - {result.error_hint}"
            if result.output:
                msg += f"\n```\n{result.output[:500]}\n```"
            return msg

    else:
        # Unknown action, try running as command
        result = _run(query)
        if result.output:
            return f"```\n{result.output}\n```"
        return "done"



def _append_context(reply: str) -> str:
    """Add lightweight context so Sel knows what she just ran."""
    parts = []
    if _state.last_command:
        parts.append(f"ran `{_state.last_command}` in `{_state.cwd}`")
    if _state.history:
        parts.append(f"{len(_state.history)} cmds this session")
    context = " • ".join(parts)
    if context:
        return f"{reply}\n\n_{context}_"
    return reply


# ============================================================================
# Compound Actions
# ============================================================================

def _check_system() -> str:
    """Quick system health overview."""
    parts = []

    # Uptime
    up = _run("uptime -p", wait_ms=300)
    if up.output:
        parts.append(f"**up** {up.output.replace('up ', '')}")

    # Load
    load = _run("cat /proc/loadavg | cut -d' ' -f1-3", wait_ms=300)
    if load.output:
        parts.append(f"**load** {load.output}")

    # Memory
    mem = _run("free -h | awk '/^Mem:/ {print $3 \"/\" $2}'", wait_ms=300)
    if mem.output:
        parts.append(f"**mem** {mem.output}")

    # Disk
    disk = _run("df -h / | awk 'NR==2 {print $3 \"/\" $2 \" (\" $5 \")\"}'", wait_ms=300)
    if disk.output:
        parts.append(f"**disk** {disk.output}")

    return " · ".join(parts)


def _check_git() -> str:
    """Git status in a friendly way."""
    # Check if we're in a repo
    check = _run("git rev-parse --is-inside-work-tree 2>/dev/null", wait_ms=300)
    if "true" not in check.output:
        return f"not in a git repo (we're in `{_state.cwd}`)"

    parts = []

    # Branch
    branch = _run("git branch --show-current", wait_ms=300)
    if branch.output:
        parts.append(f"on `{branch.output.strip()}`")

    # Status
    status = _run("git status -s", wait_ms=500)
    if status.output.strip():
        lines = status.output.strip().split("\n")
        parts.append(f"{len(lines)} changed files")
        parts.append(f"```\n{status.output.strip()}\n```")
    else:
        parts.append("clean working tree")

    # Recent commits
    log = _run("git log --oneline -3", wait_ms=500)
    if log.output:
        parts.append(f"recent:\n```\n{log.output}\n```")

    return "\n".join(parts)


# ============================================================================
# Background Jobs
# ============================================================================

def _start_job(name: str, cmd: str) -> str:
    """Start something in the background."""
    if name in _state.jobs:
        return f"`{name}` is already running - stop it first"

    full_cmd = f"cd {_state.cwd} && {cmd}"
    log_path = LOG_DIR / f"{name}.log"
    try:
        with open(log_path, "w") as log_file:
            proc = subprocess.Popen(
                full_cmd,
                shell=True,
                cwd=_state.cwd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
    except Exception as exc:
        return f"couldn't start: {exc}"

    _state.jobs[name] = {"pid": str(proc.pid), "log": str(log_path)}
    return f"started `{name}` (pid {proc.pid}) running `{cmd}`"


def _list_jobs() -> str:
    """What's running in the background."""
    if not _state.jobs:
        return "no background jobs"

    lines = []
    for name, info in list(_state.jobs.items()):
        pid = info.get("pid")
        try:
            os.kill(int(pid), 0)
            lines.append(f"• `{name}` - running (pid {pid})")
        except OSError:
            lines.append(f"• `{name}` - ended")
            del _state.jobs[name]

    return "\n".join(lines) if lines else "no background jobs"


def _check_job(name: str) -> str:
    """See what a background job is up to."""
    if name not in _state.jobs:
        return f"no job called `{name}`"

    info = _state.jobs[name]
    pid = info.get("pid")
    log_path = info.get("log")
    try:
        os.kill(int(pid), 0)
    except OSError:
        del _state.jobs[name]
        return f"`{name}` ended"

    output = ""
    if log_path and os.path.exists(log_path):
        try:
            with open(log_path, "r") as log_file:
                output = log_file.read().strip()
        except Exception:
            output = ""

    if not output:
        return f"`{name}` has no output yet"

    lines = output.split("\n")
    if len(lines) > 25:
        output = "\n".join(lines[-25:])

    return f"`{name}` output:\n```\n{output}\n```"


def _stop_job(name: str) -> str:
    """Stop a background job."""
    if name not in _state.jobs:
        return f"no job called `{name}`"

    pid = _state.jobs[name].get("pid")
    log_path = _state.jobs[name].get("log")
    try:
        os.kill(int(pid), 15)
    except Exception:
        pass
    if log_path and os.path.exists(log_path):
        try:
            os.remove(log_path)
        except Exception:
            pass
    del _state.jobs[name]
    return f"stopped `{name}`"


# ============================================================================
# Help
# ============================================================================

def _show_help() -> str:
    """Just explain naturally."""
    return """i can help with system stuff - just ask naturally:

**looking around**: "where am i", "go to projects", "what's in /tmp"
**system health**: "how's the system", "disk space", "memory usage"
**processes**: "what's running", "processes using python", "port 3000"
**services**: "docker status", "service nginx", "restart container X"
**git**: "git status", "pull latest"
**files**: "large files", "show config.py"
**background**: "start job dev npm run dev", "check job dev", "stop job dev"
**move around**: "cd repo", "cd ..", "home", "go to /var/log"

or just tell me what to run and i'll do it"""


# ============================================================================
# Entry Point
# ============================================================================

def run(query: str, **kwargs) -> str:
    """
    Sel's system interface. Talk naturally.
    """
    def _inline_cd(text: str) -> Optional[str]:
        lowered = text.strip().lower()
        if lowered in {"home", "cd ~", "cd ~/", "reset cwd", "go home"}:
            _state.cwd = HOME
            return _go(HOME)
        match = re.match(r"^cd\s+(.+)$", text.strip(), flags=re.IGNORECASE)
        if match:
            return _go(match.group(1).strip())
        match = re.match(r"^(go|jump)\s+to\s+(.+)$", text.strip(), flags=re.IGNORECASE)
        if match:
            return _go(match.group(2).strip())
        return None

    if not query.strip():
        return _append_context(_show_help())

    cd_result = _inline_cd(query)
    if cd_result:
        return _append_context(cd_result)

    return _append_context(_understand(query))
