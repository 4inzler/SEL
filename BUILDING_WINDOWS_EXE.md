# Building the Windows Executable

This guide explains how to build the Windows executable for SEL.

## Prerequisites

- Windows 10/11
- Python 3.11+
- Git (to clone the repository)

## Building the Executable

### Method 1: Using the Batch Script

1. Open Command Prompt or PowerShell in the repository root
2. Run the build script:
   ```batch
   build_windows_exe.bat
   ```
3. Wait for the build to complete (may take 2-5 minutes)
4. Find the executable at `dist/sel_launcher.exe`

### Method 2: Manual Build

1. Install PyInstaller:
   ```powershell
   pip install pyinstaller
   ```

2. Build the executable:
   ```powershell
   pyinstaller sel_windows.spec
   ```

3. The executable will be created at `dist/sel_launcher.exe`

## Distributing the Executable

To create a distribution package for users:

1. **Create a distribution folder**:
   ```
   SEL-Windows/
   ├── sel_launcher.exe          (from dist/)
   ├── project_echo/             (entire directory)
   ├── agents/                   (entire directory)
   ├── .env.example
   ├── WINDOWS_SETUP.md
   └── README.md
   ```

2. **Create a ZIP file** of the distribution folder

3. **Users install by**:
   - Extracting the ZIP file
   - Running `sel_launcher.exe`
   - Following the on-screen prompts

## What the Executable Does

The `sel_launcher.exe` handles:

1. **Dependency checking**:
   - Verifies Python 3.11+ is installed
   - Installs Poetry if missing
   - Sets up virtual environment

2. **Project setup**:
   - Installs all Python dependencies via Poetry
   - Creates data directories
   - Sets up `.env` from template

3. **Running SEL**:
   - Starts HIM service (background)
   - Starts Discord bot (foreground)
   - Handles graceful shutdown

## Alternative Distribution Methods

### Method 1: Batch Files Only

If you don't want to build an executable, you can distribute:
- `install_sel.ps1` - PowerShell installer
- `start_sel.bat` - Batch launcher
- Full repository contents

Users run:
1. `install_sel.ps1` to set up
2. Edit `.env`
3. `start_sel.bat` to start

### Method 2: Python Script

Distribute `windows_launcher.py` and users run:
```powershell
python windows_launcher.py
```

This is lighter than the executable but requires Python to be pre-installed.

## Build Customization

Edit `sel_windows.spec` to customize:

- **Add an icon**: Set `icon='path/to/icon.ico'`
- **Change name**: Modify `name='sel_launcher'`
- **Console vs GUI**: Set `console=False` for no console window
- **Include data files**: Add to `datas=[]` parameter

Example with custom icon:
```python
exe = EXE(
    # ... other parameters ...
    name='sel_launcher',
    console=True,
    icon='sel_icon.ico',  # Add your icon
)
```

## Troubleshooting Build Issues

### "PyInstaller not found"
```powershell
pip install --upgrade pyinstaller
```

### "Failed to execute script"
- Ensure Python 3.11+ is used
- Try rebuilding with `--clean` flag:
  ```powershell
  pyinstaller --clean sel_windows.spec
  ```

### Large executable size
This is normal for PyInstaller. The exe includes:
- Python interpreter
- Required standard library modules
- Launcher script

Typical size: 10-15 MB

### Antivirus false positives
Some antivirus software flags PyInstaller executables. This is a known issue:
- Test the executable in a safe environment
- Consider code signing (requires certificate)
- Or distribute as Python script instead

## Testing the Executable

Before distributing:

1. **Test on clean Windows VM**:
   - Without Python installed
   - Without Poetry installed
   - Fresh user account

2. **Verify it handles**:
   - Missing Python
   - Missing Poetry  
   - Missing .env file
   - First-time setup
   - Subsequent launches

3. **Check error handling**:
   - Invalid tokens
   - Network issues
   - Missing dependencies

## Updating the Executable

When updating SEL:

1. Pull latest code from repository
2. Test changes locally
3. Rebuild executable: `build_windows_exe.bat`
4. Test the new executable
5. Redistribute with updated version number

## Size Optimization (Optional)

To reduce executable size:

1. **Use UPX compression** (already enabled in spec):
   - Download UPX from https://upx.github.io/
   - Place in PATH or PyInstaller directory
   - Reduces size by ~40%

2. **Exclude unused modules**:
   ```python
   excludes=['tkinter', 'matplotlib', 'scipy', ...]
   ```

3. **One-folder mode** (multiple files):
   ```powershell
   pyinstaller --onedir sel_windows.spec
   ```
   - Smaller launcher.exe
   - But requires distributing entire folder

## License Considerations

When distributing:
- Include LICENSE.md
- Respect third-party licenses (Discord.py, FastAPI, etc.)
- Note that PyInstaller bundles Python interpreter (PSF License)

## Security Notes

The executable:
- Does NOT include tokens (users provide via .env)
- Does NOT phone home
- Only network access: Discord API, OpenRouter API, HIM service (local)
- Runs with user privileges (no admin required)

## Support for Users

Provide users with:
- `WINDOWS_SETUP.md` - Installation guide
- `README.md` - General information
- Discord invite or support channel
- GitHub issues link for bug reports

---

For questions about building or distributing, refer to:
- PyInstaller docs: https://pyinstaller.org/
- SEL documentation: CLAUDE.md, AGENTS.md
