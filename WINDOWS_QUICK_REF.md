# 🪟 Windows Quick Reference

## For End Users

### First Time Setup
1. Ensure Python 3.11+ is installed → https://www.python.org/downloads/
2. Run: `install_sel.ps1` (right-click → Run with PowerShell)
3. Edit `.env` file with your tokens
4. Run: `start_sel.bat`

### Every Time After
- Just run: `start_sel.bat`

### Using the Executable (if available)
- Just run: `sel_launcher.exe` (handles everything)

## For Developers

### Building the Executable
```powershell
# Windows
build_windows_exe.bat

# Or manually
pip install pyinstaller
pyinstaller sel_windows.spec
# Output: dist/sel_launcher.exe
```

### Testing Changes
```powershell
cd project_echo
poetry run pytest
```

### Manual Launch (for debugging)
```powershell
cd project_echo

# Terminal 1: HIM service
poetry run python run_him.py --data-dir ./data

# Terminal 2: Discord bot
poetry run python -m sel_bot.main
```

## File Reference

| File | Purpose | When to Use |
|------|---------|-------------|
| `sel_launcher.exe` | All-in-one executable | Easiest for end users |
| `start_sel.bat` | Quick launcher | After initial setup |
| `install_sel.ps1` | Setup script | First time installation |
| `windows_launcher.py` | Launcher source | For building exe |
| `sel_windows.spec` | PyInstaller config | For building exe |
| `build_windows_exe.bat` | Build script | To create exe |
| `.env` | Configuration | Store tokens here |
| `WINDOWS_README.md` | User guide | Help for beginners |
| `WINDOWS_SETUP.md` | Detailed guide | Troubleshooting |
| `BUILDING_WINDOWS_EXE.md` | Dev guide | Building/distributing |

## Common Commands

### Installation
```powershell
# Install dependencies
.\install_sel.ps1

# Or manually
cd project_echo
poetry install
```

### Running
```powershell
# Quick start
.\start_sel.bat

# Or manually with Poetry
cd project_echo
poetry run python -m sel_bot.main
```

### Building
```powershell
# Build executable
.\build_windows_exe.bat

# Or manually
pyinstaller sel_windows.spec
```

## Environment Variables

Required in `.env`:
```env
DISCORD_BOT_TOKEN=your_token_here
OPENROUTER_API_KEY=your_key_here
```

Optional (common):
```env
HIM_ENABLED=1
HIM_PORT=8000
DATABASE_URL=sqlite+aiosqlite:///./sel.db
OPENROUTER_MAIN_MODEL=anthropic/claude-3.5-sonnet
```

## Troubleshooting Quick Fixes

| Problem | Solution |
|---------|----------|
| Python not found | Install Python 3.11+, check "Add to PATH" |
| Poetry not found | Run `install_sel.ps1` or install manually |
| Bot doesn't respond | Check tokens in `.env`, verify Discord permissions |
| Port in use | Change `HIM_PORT` in `.env` |
| Module not found | Run `poetry install` in `project_echo/` |
| Script won't run | PowerShell: `Set-ExecutionPolicy RemoteSigned` |

## Getting Help

1. Check `WINDOWS_SETUP.md` for detailed troubleshooting
2. Review console output for error messages
3. Verify `.env` configuration
4. Check Discord bot permissions and intents
5. Ensure OpenRouter API key is valid

## Distribution Checklist

When sharing SEL with others:
- [ ] Include `sel_launcher.exe` (or `start_sel.bat` + `install_sel.ps1`)
- [ ] Include entire `project_echo/` directory
- [ ] Include `agents/` directory
- [ ] Include `.env.example` (NOT `.env` with your tokens!)
- [ ] Include `WINDOWS_README.md` and `WINDOWS_SETUP.md`
- [ ] Include `LICENSE.md`

## Quick Links

- **Main Docs**: `README.md`, `CLAUDE.md`
- **Windows Guide**: `WINDOWS_SETUP.md`
- **User Guide**: `WINDOWS_README.md`
- **Build Guide**: `BUILDING_WINDOWS_EXE.md`
- **Implementation**: `WINDOWS_IMPLEMENTATION.md`

---

**Need more help?** See `WINDOWS_SETUP.md` for comprehensive documentation.
