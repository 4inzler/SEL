"""
SEL Bot Windows Launcher
Single-file executable wrapper for Windows that handles installation and startup.
Build with: pyinstaller --onefile --name sel_windows_launcher windows_launcher.py
"""

import os
import sys
import subprocess
import shutil
import json
import time
import urllib.request
from pathlib import Path
from typing import Optional


class Colors:
    """ANSI color codes for terminal output"""
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_colored(message: str, color: str = Colors.RESET):
    """Print colored message to console"""
    print(f"{color}{message}{Colors.RESET}")


def print_header(message: str):
    """Print a formatted header"""
    print()
    print_colored("=" * 60, Colors.CYAN)
    print_colored(f"  {message}", Colors.CYAN + Colors.BOLD)
    print_colored("=" * 60, Colors.CYAN)
    print()


def check_command(command: str) -> bool:
    """Check if a command exists in PATH"""
    return shutil.which(command) is not None


def get_python_version() -> Optional[tuple]:
    """Get Python version as tuple (major, minor)"""
    try:
        result = subprocess.run(
            ["python", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        version_str = result.stdout or result.stderr
        if "Python" in version_str:
            parts = version_str.split()[1].split('.')
            return (int(parts[0]), int(parts[1]))
    except Exception:
        pass
    return None


def check_python() -> bool:
    """Check Python installation and version"""
    print_colored("Checking Python installation...", Colors.GREEN)
    
    if not check_command("python"):
        print_colored("❌ Python not found in PATH", Colors.RED)
        print_colored("Please install Python 3.11+ from: https://www.python.org/downloads/", Colors.YELLOW)
        print_colored("Make sure to check 'Add Python to PATH' during installation!", Colors.YELLOW)
        return False
    
    version = get_python_version()
    if version is None:
        print_colored("⚠️  Could not determine Python version", Colors.YELLOW)
        return False
    
    major, minor = version
    print_colored(f"✅ Found Python {major}.{minor}", Colors.CYAN)
    
    if major < 3 or (major == 3 and minor < 11):
        print_colored(f"❌ Python 3.11+ required, found {major}.{minor}", Colors.RED)
        print_colored("Please upgrade from: https://www.python.org/downloads/", Colors.YELLOW)
        return False
    
    return True


def install_poetry() -> bool:
    """Install Poetry if not present"""
    print()
    print_colored("Checking Poetry installation...", Colors.GREEN)
    
    if check_command("poetry"):
        try:
            result = subprocess.run(
                ["poetry", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            print_colored(f"✅ Found {result.stdout.strip()}", Colors.CYAN)
            return True
        except Exception:
            pass
    
    print_colored("Poetry not found. Installing...", Colors.YELLOW)
    
    try:
        # Download and run Poetry installer
        installer_url = "https://install.python-poetry.org"
        response = urllib.request.urlopen(installer_url, timeout=30)
        installer_script = response.read()
        
        # Run installer through Python
        result = subprocess.run(
            ["python", "-c", installer_script.decode()],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            # Add Poetry to PATH for current session
            poetry_path = Path(os.environ.get("APPDATA", "")) / "Python" / "Scripts"
            if poetry_path.exists():
                os.environ["PATH"] = f"{poetry_path};{os.environ['PATH']}"
                print_colored("✅ Poetry installed successfully!", Colors.GREEN)
                return True
        
        print_colored("❌ Failed to install Poetry", Colors.RED)
        print_colored("Please install manually: https://python-poetry.org/docs/#installation", Colors.YELLOW)
        return False
        
    except Exception as e:
        print_colored(f"❌ Error installing Poetry: {e}", Colors.RED)
        print_colored("Please install manually: https://python-poetry.org/docs/#installation", Colors.YELLOW)
        return False


def setup_project(base_dir: Path) -> bool:
    """Install project dependencies"""
    print()
    print_colored("Setting up project dependencies...", Colors.GREEN)
    
    project_dir = base_dir / "project_echo"
    if not project_dir.exists():
        print_colored(f"❌ project_echo directory not found at {project_dir}", Colors.RED)
        return False
    
    os.chdir(project_dir)
    
    # Configure Poetry to create venv in project
    subprocess.run(
        ["poetry", "config", "virtualenvs.in-project", "true"],
        capture_output=True,
        timeout=10
    )
    
    print_colored("Installing Python dependencies (this may take a few minutes)...", Colors.YELLOW)
    
    try:
        result = subprocess.run(
            ["poetry", "install"],
            capture_output=False,  # Show output
            timeout=600  # 10 minutes
        )
        
        if result.returncode == 0:
            print_colored("✅ Dependencies installed successfully!", Colors.GREEN)
            return True
        else:
            print_colored("❌ Failed to install dependencies", Colors.RED)
            return False
            
    except subprocess.TimeoutExpired:
        print_colored("❌ Installation timed out", Colors.RED)
        return False
    except Exception as e:
        print_colored(f"❌ Error during installation: {e}", Colors.RED)
        return False


def create_env_file(base_dir: Path):
    """Create .env file from example if it doesn't exist"""
    env_file = base_dir / ".env"
    env_example = base_dir / ".env.example"
    
    if not env_file.exists() and env_example.exists():
        shutil.copy(env_example, env_file)
        print()
        print_colored("✅ Created .env file from template", Colors.GREEN)
        print_colored("⚠️  IMPORTANT: Edit .env and add your tokens:", Colors.YELLOW)
        print_colored("   - DISCORD_BOT_TOKEN", Colors.YELLOW)
        print_colored("   - OPENROUTER_API_KEY", Colors.YELLOW)
        return False  # Indicate env needs configuration
    elif not env_file.exists():
        print_colored("⚠️  No .env file found. Create one with your tokens.", Colors.YELLOW)
        return False
    
    return True  # Env file exists


def load_env_file(base_dir: Path) -> dict:
    """Load environment variables from .env file"""
    env_file = base_dir / ".env"
    env_vars = {}
    
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    
    return env_vars


def start_sel(base_dir: Path):
    """Start SEL bot and HIM service"""
    print_header("Starting SEL Bot")
    
    # Load environment
    env_vars = load_env_file(base_dir)
    
    # Check required variables
    if not env_vars.get("DISCORD_BOT_TOKEN"):
        print_colored("❌ DISCORD_BOT_TOKEN not set in .env file", Colors.RED)
        return False
    
    if not env_vars.get("OPENROUTER_API_KEY"):
        print_colored("❌ OPENROUTER_API_KEY not set in .env file", Colors.RED)
        return False
    
    # Set defaults
    him_enabled = env_vars.get("HIM_ENABLED", "1")
    him_port = env_vars.get("HIM_PORT", "8000")
    
    project_dir = base_dir / "project_echo"
    data_dir = project_dir / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Set environment for subprocesses
    env = os.environ.copy()
    env.update(env_vars)
    env["HIM_DATA_DIR"] = str(data_dir)
    env["HIM_MEMORY_DIR"] = str(data_dir / "him_store")
    
    os.chdir(project_dir)
    
    him_process = None
    
    try:
        # Start HIM service if enabled
        if him_enabled == "1":
            print_colored(f"Starting HIM service on port {him_port}...", Colors.CYAN)
            him_process = subprocess.Popen(
                [
                    "poetry", "run", "python", "run_him.py",
                    "--data-dir", str(data_dir),
                    "--host", "127.0.0.1",
                    "--port", him_port,
                    "--skip-hardware-checks"
                ],
                env=env,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )
            print_colored("✅ HIM service started", Colors.GREEN)
            time.sleep(3)  # Wait for HIM to initialize
        
        # Start Discord bot (foreground)
        print()
        print_colored("Starting SEL Discord bot...", Colors.CYAN)
        print_colored("Press Ctrl+C to stop", Colors.YELLOW)
        print()
        
        bot_process = subprocess.Popen(
            ["poetry", "run", "python", "-m", "sel_bot.main"],
            env=env
        )
        
        # Wait for bot to exit
        bot_process.wait()
        
    except KeyboardInterrupt:
        print()
        print_colored("Shutting down...", Colors.YELLOW)
    finally:
        # Cleanup
        if him_process:
            him_process.terminate()
            try:
                him_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                him_process.kill()
        
        print_colored("✅ SEL Bot stopped", Colors.GREEN)


def main():
    """Main entry point"""
    print_header("SEL Bot - Windows Launcher")
    
    # Get base directory (where the exe is located)
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_dir = Path(sys.executable).parent
    else:
        # Running as script
        base_dir = Path(__file__).parent
    
    print_colored(f"Working directory: {base_dir}", Colors.CYAN)
    
    # Installation phase
    if not check_python():
        input("\nPress Enter to exit...")
        return 1
    
    if not install_poetry():
        input("\nPress Enter to exit...")
        return 1
    
    # Check if project needs setup
    project_dir = base_dir / "project_echo"
    venv_dir = project_dir / ".venv"
    
    if not venv_dir.exists():
        print()
        print_colored("First-time setup detected", Colors.YELLOW)
        if not setup_project(base_dir):
            input("\nPress Enter to exit...")
            return 1
    
    # Check .env configuration
    env_configured = create_env_file(base_dir)
    
    if not env_configured:
        print()
        print_colored("Please configure your .env file before continuing", Colors.YELLOW)
        input("\nPress Enter to exit...")
        return 0
    
    # Start the bot
    print()
    start_sel(base_dir)
    
    input("\nPress Enter to exit...")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print_colored(f"\n❌ Fatal error: {e}", Colors.RED)
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)
