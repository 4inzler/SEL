# SEL Bot - Windows Setup Guide

This guide will help you get SEL running on Windows. SEL is a Discord presence bot with hierarchical memory and emotional state tracking.

## Quick Start (Recommended)

### Option 1: Using the Launcher Executable

1. **Download the complete package** containing:
   - `sel_launcher.exe` (Windows executable)
   - `project_echo/` directory (bot code and dependencies)
   - `.env.example` (configuration template)

2. **Run the launcher**:
   - Double-click `sel_launcher.exe`
   - The launcher will automatically:
     - Check for Python 3.11+ (and guide you to install if missing)
     - Install Poetry if needed
     - Set up all dependencies
     - Create `.env` file from template

3. **Configure your tokens**:
   - Edit `.env` file in the root directory
   - Add your `DISCORD_BOT_TOKEN` and `OPENROUTER_API_KEY`
   - Save the file

4. **Run again**:
   - Double-click `sel_launcher.exe` again to start SEL
   - The bot will launch with HIM (Hierarchical Image Memory) service

### Option 2: Using Batch Files

1. **Prerequisites**:
   - Install [Python 3.11+](https://www.python.org/downloads/) 
     - ⚠️ **Important**: Check "Add Python to PATH" during installation!

2. **Install dependencies**:
   - Right-click `install_sel.ps1`
   - Select "Run with PowerShell"
   - Or open PowerShell and run: `.\install_sel.ps1`

3. **Configure tokens**:
   - Edit `.env` file (created from `.env.example`)
   - Add your Discord bot token and OpenRouter API key

4. **Start SEL**:
   - Double-click `start_sel.bat`
   - Two windows will open:
     - HIM service (background, minimized)
     - SEL Discord bot (foreground)

## Manual Installation

If you prefer manual control:

### 1. Install Prerequisites

- **Python 3.11+**: https://www.python.org/downloads/
  - During installation, check "Add Python to PATH"
  - Verify: `python --version`

- **Poetry** (Python dependency manager):
  ```powershell
  # In PowerShell or Command Prompt
  curl -sSL https://install.python-poetry.org | python -
  ```
  - Add to PATH: `%APPDATA%\Python\Scripts`

### 2. Install Dependencies

```powershell
# Navigate to project_echo directory
cd project_echo

# Configure Poetry to use project-local virtualenv
poetry config virtualenvs.in-project true

# Install dependencies
poetry install
```

### 3. Configure Environment

Create `.env` in the repository root:

```env
# Required
DISCORD_BOT_TOKEN=your_discord_bot_token_here
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Optional - Model configuration
OPENROUTER_MAIN_MODEL=anthropic/claude-3.5-sonnet
OPENROUTER_UTIL_MODEL=anthropic/claude-3-haiku-20240307
OPENROUTER_MAIN_TEMP=0.8
OPENROUTER_UTIL_TEMP=0.3

# Optional - Database (defaults to SQLite)
DATABASE_URL=sqlite+aiosqlite:///./sel.db

# Optional - HIM configuration
HIM_ENABLED=1
HIM_PORT=8000
```

### 4. Start SEL

#### Option A: Start Everything Together

```powershell
# From repository root
start_sel.bat
```

#### Option B: Start Services Separately

Terminal 1 (HIM Service):
```powershell
cd project_echo
poetry run python run_him.py --data-dir ./data --host 127.0.0.1 --port 8000
```

Terminal 2 (Discord Bot):
```powershell
cd project_echo
poetry run python -m sel_bot.main
```

## Getting Discord Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section
4. Click "Reset Token" and copy it
5. Enable these **Privileged Gateway Intents**:
   - Presence Intent
   - Server Members Intent
   - Message Content Intent
6. Go to OAuth2 → URL Generator
7. Select scopes: `bot`
8. Select permissions: 
   - Read Messages/View Channels
   - Send Messages
   - Read Message History
9. Copy the generated URL and invite the bot to your server

## Getting OpenRouter API Key

1. Go to [OpenRouter](https://openrouter.ai/)
2. Sign up or log in
3. Go to [Keys section](https://openrouter.ai/keys)
4. Create a new API key
5. Copy the key (starts with `sk-or-v1-...`)

## Troubleshooting

### "Python not found"

- Make sure Python 3.11+ is installed
- Verify Python is in PATH: `python --version`
- If not, reinstall Python and check "Add Python to PATH"
- Or manually add Python to PATH in System Environment Variables

### "Poetry not found"

- Install Poetry: `(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -`
- Add Poetry to PATH: `%APPDATA%\Python\Scripts`
- Restart your terminal after adding to PATH

### "Module not found" errors

```powershell
cd project_echo
poetry install --no-cache
```

### Bot doesn't respond

1. Check bot token is correct in `.env`
2. Verify bot has proper permissions on Discord
3. Check Message Content Intent is enabled
4. Look at console output for errors

### HIM service fails to start

- Check if port 8000 is available
- Try a different port: set `HIM_PORT=8001` in `.env`
- Check data directory permissions
- Disable HIM temporarily: set `HIM_ENABLED=0` in `.env`

### "Access Denied" when running PowerShell script

```powershell
# Run PowerShell as Administrator
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then try running the script again.

## File Structure

```
sel/
├── sel_launcher.exe         # Windows launcher (optional)
├── start_sel.bat            # Quick start script
├── install_sel.ps1          # Installation script
├── windows_launcher.py      # Source for launcher exe
├── .env                     # Your configuration (create from .env.example)
├── .env.example             # Configuration template
└── project_echo/
    ├── sel_bot/             # Discord bot code
    ├── him/                 # Hierarchical Image Memory
    ├── run_him.py           # HIM service entry point
    ├── pyproject.toml       # Poetry dependencies
    └── data/                # Runtime data (created automatically)
        ├── sel.db           # SQLite database
        └── him_store/       # Memory tiles
```

## Configuration Options

Edit `.env` to customize SEL's behavior:

### Core Settings
- `DISCORD_BOT_TOKEN`: Your Discord bot token (required)
- `OPENROUTER_API_KEY`: Your OpenRouter API key (required)
- `DATABASE_URL`: Database connection string (default: SQLite)

### LLM Models
- `OPENROUTER_MAIN_MODEL`: Primary conversational model
- `OPENROUTER_UTIL_MODEL`: Utility/classification model
- `OPENROUTER_VISION_MODEL`: Image analysis model
- `OPENROUTER_MAIN_TEMP`: Temperature for main model (0.0-1.0)
- `OPENROUTER_UTIL_TEMP`: Temperature for utility model (0.0-1.0)

### Memory System
- `HIM_ENABLED`: Enable HIM service (0 or 1)
- `HIM_PORT`: Port for HIM API (default: 8000)
- `HIM_MEMORY_DIR`: Directory for memory tiles
- `MEMORY_RECALL_LIMIT`: Max memories to recall (default: 10)
- `RECENT_CONTEXT_LIMIT`: Recent messages to include (default: 20)

### Bot Behavior
- `SEL_PERSONA_SEED`: Base personality prompt
- `WHITELIST_CHANNEL_IDS`: Comma-separated channel IDs (blank = all channels)
- `APPROVAL_USER_ID`: User ID authorized for system commands
- `INACTIVITY_PING_HOURS`: Hours before proactive ping (default: 48)

## Building the Executable (Advanced)

To rebuild `sel_launcher.exe` from source:

1. Install PyInstaller:
   ```powershell
   pip install pyinstaller
   ```

2. Build the executable:
   ```powershell
   pyinstaller sel_windows.spec
   ```

3. Find the executable:
   ```
   dist/sel_launcher.exe
   ```

## System Agent Features (Windows-Specific)

When running on Windows, SEL's system agent can:
- Check system information
- Monitor processes and resources
- List files and directories
- Execute safe system commands (authorized users only)

**Note**: The system agent uses `tmux_control_api.py` which is Linux-focused. On Windows, some system features may have limited functionality. Consider running SEL in WSL2 for full system agent capabilities.

## Running in WSL2 (Alternative)

For better system integration, you can run SEL in Windows Subsystem for Linux:

1. Install WSL2 with Ubuntu
2. Clone the repository in WSL
3. Follow the Linux installation instructions from `README.md`
4. The bot will still connect to Discord and work normally

## Performance Tips

- **First run** may take 5-10 minutes to install dependencies
- **Memory usage**: Expect 500MB-1GB RAM usage (varies with model calls)
- **Storage**: ~500MB for installation, plus runtime data in `data/`
- **HIM service**: Adds ~100-200MB RAM overhead

## Updates

To update SEL to the latest version:

```powershell
cd project_echo
git pull origin main
poetry install
```

## Support

For issues and questions:
- Check existing GitHub issues
- Review logs in console output
- Verify `.env` configuration
- Ensure Discord bot permissions are correct

## Advanced: Using Docker on Windows

If you have Docker Desktop for Windows:

1. Enable WSL2 backend in Docker Desktop settings
2. From repository root:
   ```powershell
   docker-compose up --build
   ```

This runs SEL in a containerized environment with PostgreSQL database.

## Uninstallation

To remove SEL:

1. Stop the bot (Ctrl+C or close windows)
2. Delete the repository folder
3. (Optional) Uninstall Poetry:
   ```powershell
   (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python - --uninstall
   ```

## Next Steps

Once SEL is running:
- Interact with the bot in Discord
- SEL will remember conversations and build emotional context
- Try asking questions or having conversations
- Authorized users can use system commands (e.g., "what's my system info?")
- SEL becomes more personalized over time through memory accumulation

Enjoy using SEL! 🤖
