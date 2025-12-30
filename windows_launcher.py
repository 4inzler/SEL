"""
SEL Bot Windows Launcher - DOCKER ONLY
Enforces Docker Desktop with WSL 2 backend for maximum security.
SEL cannot run natively on Windows - Docker containerization is REQUIRED.

Build with: pyinstaller --onefile --icon=sel_icon.ico --name sel_launcher windows_launcher.py
"""

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from typing import Optional, Tuple

# Fix Windows console encoding for emoji support
if sys.platform == "win32":
    try:
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
    except Exception:
        pass


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
    print_colored("=" * 70, Colors.CYAN)
    print_colored(f"  {message}", Colors.CYAN + Colors.BOLD)
    print_colored("=" * 70, Colors.CYAN)
    print()


def print_error_header(message: str):
    """Print a formatted error header"""
    print()
    print_colored("=" * 70, Colors.RED)
    print_colored(f"  ❌ {message}", Colors.RED + Colors.BOLD)
    print_colored("=" * 70, Colors.RED)
    print()


def run_command(cmd: list, timeout: int = 10) -> Tuple[bool, str]:
    """Run a command and return (success, output)"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return (result.returncode == 0, result.stdout.strip())
    except subprocess.TimeoutExpired:
        return (False, "Command timed out")
    except FileNotFoundError:
        return (False, "Command not found")
    except Exception as e:
        return (False, str(e))


def check_docker_desktop_installed() -> bool:
    """Check if Docker Desktop is installed on Windows"""
    print_colored("[1/5] Checking Docker Desktop installation...", Colors.CYAN)

    # Check if docker command exists
    success, output = run_command(["docker", "--version"])

    if not success:
        print_error_header("DOCKER DESKTOP NOT INSTALLED")
        print_colored("SEL requires Docker Desktop for Windows to run securely.", Colors.YELLOW)
        print()
        print_colored("Installation Steps:", Colors.CYAN)
        print_colored("1. Download Docker Desktop from:", Colors.WHITE)
        print_colored("   https://www.docker.com/products/docker-desktop", Colors.GREEN)
        print()
        print_colored("2. Run the installer (requires Administrator)", Colors.WHITE)
        print_colored("3. Enable 'Use WSL 2 instead of Hyper-V' during setup", Colors.WHITE)
        print_colored("4. Restart your computer", Colors.WHITE)
        print_colored("5. Launch Docker Desktop and complete setup", Colors.WHITE)
        print()
        print_colored("System Requirements:", Colors.CYAN)
        print_colored("• Windows 10/11 64-bit: Pro, Enterprise, or Education", Colors.WHITE)
        print_colored("• WSL 2 feature enabled", Colors.WHITE)
        print_colored("• Virtualization enabled in BIOS", Colors.WHITE)
        print_colored("• 4GB RAM minimum (8GB recommended)", Colors.WHITE)
        print()
        return False

    print_colored(f"  ✅ Docker Desktop found: {output}", Colors.GREEN)
    return True


def check_docker_running() -> bool:
    """Check if Docker Desktop is running"""
    print_colored("[2/5] Checking Docker Desktop status...", Colors.CYAN)

    success, output = run_command(["docker", "info"], timeout=5)

    if not success:
        print_error_header("DOCKER DESKTOP NOT RUNNING")
        print_colored("Docker Desktop is installed but not running.", Colors.YELLOW)
        print()
        print_colored("To start Docker Desktop:", Colors.CYAN)
        print_colored("1. Press Windows Key", Colors.WHITE)
        print_colored("2. Type 'Docker Desktop'", Colors.WHITE)
        print_colored("3. Click 'Docker Desktop' to launch", Colors.WHITE)
        print_colored("4. Wait for Docker to fully start (whale icon in system tray)", Colors.WHITE)
        print_colored("5. Run this launcher again", Colors.WHITE)
        print()
        print_colored("Alternative: Launch from Start Menu", Colors.CYAN)
        return False

    print_colored("  ✅ Docker Desktop is running", Colors.GREEN)
    return True


def check_wsl2_backend() -> bool:
    """Check if Docker Desktop is using WSL 2 backend"""
    print_colored("[3/5] Verifying WSL 2 backend...", Colors.CYAN)

    # Check Docker info for WSL
    success, output = run_command(["docker", "info", "--format", "{{.OperatingSystem}}"])

    if not success:
        print_colored("  ⚠️  Could not verify Docker backend", Colors.YELLOW)
        return True  # Continue anyway

    # Check for WSL indicators
    is_wsl = "WSL" in output or "wsl" in output.lower()

    if not is_wsl:
        print_error_header("WSL 2 BACKEND NOT ENABLED")
        print_colored("Docker Desktop must use WSL 2 backend for SEL.", Colors.YELLOW)
        print()
        print_colored("To enable WSL 2 backend:", Colors.CYAN)
        print_colored("1. Right-click Docker Desktop icon in system tray", Colors.WHITE)
        print_colored("2. Click 'Settings'", Colors.WHITE)
        print_colored("3. Go to 'General'", Colors.WHITE)
        print_colored("4. Check ✓ 'Use the WSL 2 based engine'", Colors.WHITE)
        print_colored("5. Click 'Apply & Restart'", Colors.WHITE)
        print()
        print_colored("If WSL 2 is not available:", Colors.CYAN)
        print_colored("Run PowerShell as Administrator and execute:", Colors.WHITE)
        print_colored("  wsl --install", Colors.GREEN)
        print_colored("  wsl --set-default-version 2", Colors.GREEN)
        print_colored("Then restart your computer.", Colors.WHITE)
        print()
        return False

    print_colored(f"  ✅ WSL 2 backend active: {output}", Colors.GREEN)
    return True


def check_docker_compose() -> bool:
    """Check if docker-compose is available"""
    print_colored("[4/5] Checking docker-compose...", Colors.CYAN)

    success, output = run_command(["docker-compose", "--version"])

    if not success:
        # Try 'docker compose' (v2 syntax)
        success, output = run_command(["docker", "compose", "version"])

        if not success:
            print_error_header("DOCKER COMPOSE NOT AVAILABLE")
            print_colored("Docker Compose is required but not found.", Colors.YELLOW)
            print_colored("This should be included with Docker Desktop.", Colors.YELLOW)
            print()
            print_colored("Please reinstall Docker Desktop from:", Colors.CYAN)
            print_colored("https://www.docker.com/products/docker-desktop", Colors.GREEN)
            return False

    print_colored(f"  ✅ Docker Compose found: {output}", Colors.GREEN)
    return True


def check_env_file(base_dir: Path) -> bool:
    """Check if .env file exists and has required variables"""
    print_colored("[5/5] Checking configuration...", Colors.CYAN)

    env_file = base_dir / ".env"

    if not env_file.exists():
        print_colored("  ⚠️  .env file not found", Colors.YELLOW)
        print()
        print_colored("Creating .env file from template...", Colors.CYAN)

        env_example = base_dir / ".env.example"
        if env_example.exists():
            env_file.write_text(env_example.read_text())
            print_colored("  ✅ Created .env file", Colors.GREEN)
        else:
            print_colored("  ❌ .env.example not found", Colors.RED)
            return False

        print()
        print_colored("=" * 70, Colors.YELLOW)
        print_colored("  ⚠️  CONFIGURATION REQUIRED", Colors.YELLOW + Colors.BOLD)
        print_colored("=" * 70, Colors.YELLOW)
        print()
        print_colored("Please edit the .env file and add your tokens:", Colors.WHITE)
        print_colored(f"  Location: {env_file}", Colors.CYAN)
        print()
        print_colored("Required values:", Colors.CYAN)
        print_colored("  DISCORD_BOT_TOKEN=your_discord_bot_token_here", Colors.WHITE)
        print_colored("  OPENROUTER_API_KEY=your_openrouter_api_key_here", Colors.WHITE)
        print()
        print_colored("After editing .env, run this launcher again.", Colors.YELLOW)
        return False

    # Check for required variables
    env_content = env_file.read_text()
    has_discord = "DISCORD_BOT_TOKEN=" in env_content and "your_discord_bot_token" not in env_content
    has_openrouter = "OPENROUTER_API_KEY=" in env_content and "your_openrouter_api_key" not in env_content

    if not has_discord or not has_openrouter:
        print_colored("  ⚠️  .env file incomplete", Colors.YELLOW)
        print()
        print_colored("=" * 70, Colors.YELLOW)
        print_colored("  ⚠️  TOKENS NOT CONFIGURED", Colors.YELLOW + Colors.BOLD)
        print_colored("=" * 70, Colors.YELLOW)
        print()
        print_colored("Please edit the .env file and add your tokens:", Colors.WHITE)
        print_colored(f"  Location: {env_file}", Colors.CYAN)
        print()
        if not has_discord:
            print_colored("  ❌ DISCORD_BOT_TOKEN not set", Colors.RED)
        if not has_openrouter:
            print_colored("  ❌ OPENROUTER_API_KEY not set", Colors.RED)
        print()
        return False

    print_colored("  ✅ Configuration file ready", Colors.GREEN)
    return True


def start_sel_docker(base_dir: Path):
    """Start SEL in Docker container"""
    print_header("Starting SEL in Secure Docker Container")

    os.chdir(base_dir)

    print_colored("Deployment options:", Colors.CYAN)
    print_colored("  1. Quick start (reuse existing container)", Colors.WHITE)
    print_colored("  2. Full rebuild (rebuild container from scratch)", Colors.WHITE)
    print_colored("  3. Deploy with automated security verification", Colors.WHITE)
    print()

    choice = input("Select option [1/2/3]: ").strip()

    print()

    if choice == "2":
        # Full rebuild
        print_colored("Building SEL container with maximum security...", Colors.CYAN)
        print_colored("This may take several minutes on first run.", Colors.YELLOW)
        print()

        result = subprocess.run(["docker-compose", "build", "--no-cache"])

        if result.returncode != 0:
            print_colored("❌ Build failed!", Colors.RED)
            return

        print_colored("✅ Build complete!", Colors.GREEN)
        print()

    if choice == "3":
        # Use automated deployment script
        print_colored("Running automated deployment with security verification...", Colors.CYAN)
        print()

        deploy_script = base_dir / "deploy-windows.ps1"
        if deploy_script.exists():
            subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(deploy_script)])
        else:
            print_colored("⚠️  deploy-windows.ps1 not found, using manual deployment", Colors.YELLOW)
            subprocess.run(["docker-compose", "up", "-d"])
    else:
        # Quick start
        print_colored("Starting SEL container...", Colors.CYAN)
        result = subprocess.run(["docker-compose", "up", "-d"])

        if result.returncode != 0:
            print_colored("❌ Failed to start container!", Colors.RED)
            return

        print_colored("✅ SEL container started!", Colors.GREEN)
        print()

        # Wait for startup
        print_colored("Waiting for SEL to initialize...", Colors.YELLOW)
        time.sleep(5)

        # Show logs
        print()
        print_colored("=" * 70, Colors.CYAN)
        print_colored("  SEL is running in Docker (press Ctrl+C to stop viewing logs)", Colors.CYAN)
        print_colored("=" * 70, Colors.CYAN)
        print()

        try:
            subprocess.run(["docker-compose", "logs", "-f", "sel-bot"])
        except KeyboardInterrupt:
            print()
            print_colored("Stopped viewing logs (SEL still running in background)", Colors.YELLOW)
            print()
            print_colored("Useful commands:", Colors.CYAN)
            print_colored("  View logs:     docker-compose logs -f sel-bot", Colors.WHITE)
            print_colored("  Stop SEL:      docker-compose down", Colors.WHITE)
            print_colored("  Restart SEL:   docker-compose restart sel-bot", Colors.WHITE)
            print_colored("  Check status:  docker ps", Colors.WHITE)
            print()


def main():
    """Main entry point"""
    print_header("SEL Bot - Secure Docker Launcher for Windows")

    print_colored("SECURITY NOTICE:", Colors.YELLOW + Colors.BOLD)
    print_colored("SEL can ONLY run in Docker Desktop with WSL 2 backend.", Colors.YELLOW)
    print_colored("Native Windows execution is disabled for security.", Colors.YELLOW)
    print()

    # Get base directory (where the exe is located)
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_dir = Path(sys.executable).parent
    else:
        # Running as script
        base_dir = Path(__file__).parent

    print_colored(f"SEL Directory: {base_dir}", Colors.CYAN)
    print()

    # Verify all requirements
    print_colored("Verifying Docker Desktop environment...", Colors.CYAN + Colors.BOLD)
    print()

    checks = [
        check_docker_desktop_installed,
        check_docker_running,
        check_wsl2_backend,
        check_docker_compose,
        lambda: check_env_file(base_dir)
    ]

    for check in checks:
        if not check():
            print()
            print_colored("=" * 70, Colors.RED)
            print_colored("  ❌ REQUIREMENTS NOT MET", Colors.RED + Colors.BOLD)
            print_colored("=" * 70, Colors.RED)
            print()
            print_colored("Please resolve the issues above and run this launcher again.", Colors.YELLOW)
            input("\nPress Enter to exit...")
            return 1
        time.sleep(0.5)  # Brief pause between checks

    print()
    print_colored("=" * 70, Colors.GREEN)
    print_colored("  ✅ ALL REQUIREMENTS MET", Colors.GREEN + Colors.BOLD)
    print_colored("=" * 70, Colors.GREEN)
    print()

    # Start SEL in Docker
    try:
        start_sel_docker(base_dir)
    except KeyboardInterrupt:
        print()
        print_colored("Interrupted by user", Colors.YELLOW)
    except Exception as e:
        print()
        print_colored(f"❌ Error: {e}", Colors.RED)
        import traceback
        traceback.print_exc()

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
