# SEL Windows Installation - Complete Guide

This is the master installation guide for SEL on Windows. Choose the method that best fits your skill level.

## 📋 Before You Start

### System Requirements
- **OS**: Windows 10 or Windows 11
- **Python**: 3.11 or higher
- **RAM**: 2GB minimum (4GB recommended)
- **Disk Space**: 500MB for installation + runtime data
- **Internet**: Required for installation and bot operation

### What You'll Need
1. **Discord Bot Token** - Get from [Discord Developer Portal](https://discord.com/developers/applications)
2. **OpenRouter API Key** - Get from [OpenRouter](https://openrouter.ai/keys)

### Pre-Installation Check (Optional)
Run `check_system.bat` to verify your system is ready.

---

## 🚀 Installation Methods

### Method 1: One-Click Executable (Easiest) ⭐

**Best for**: Complete beginners, non-technical users

**Steps**:
1. Download the distribution package (includes `sel_launcher.exe`)
2. Extract to a folder (e.g., `C:\SEL\`)
3. Double-click `sel_launcher.exe`
4. Follow the on-screen prompts:
   - It will check for Python (guide you to install if missing)
   - It will install Poetry automatically
   - It will set up all dependencies
5. When prompted, edit `.env` file:
   - Open with Notepad
   - Add your `DISCORD_BOT_TOKEN`
   - Add your `OPENROUTER_API_KEY`
   - Save and close
6. Run `sel_launcher.exe` again
7. SEL starts! 🎉

**Pros**: 
- No prerequisites needed
- Automatic setup
- User-friendly error messages

**Cons**:
- Larger download size
- May trigger antivirus warnings

---

### Method 2: PowerShell Installer (Recommended) ⭐⭐

**Best for**: Most Windows users, those comfortable with command line

**Prerequisites**:
- Python 3.11+ installed ([Download](https://www.python.org/downloads/))
  - ⚠️ Check "Add Python to PATH" during installation!

**Steps**:

1. **Download and extract** the SEL repository

2. **Run the installer**:
   - Right-click `install_sel.ps1`
   - Select "Run with PowerShell"
   - Or open PowerShell in the SEL folder:
     ```powershell
     .\install_sel.ps1
     ```

3. **Wait for installation** (5-10 minutes):
   - Poetry will be installed
   - Dependencies will be downloaded
   - Virtual environment will be created

4. **Configure tokens**:
   - Open `.env` in Notepad (created from `.env.example`)
   - Add your Discord bot token and OpenRouter API key
   - Save the file

5. **Launch SEL**:
   - Double-click `start_sel.bat`
   - Or run in Command Prompt:
     ```batch
     start_sel.bat
     ```

6. **Two windows open**:
   - HIM Service (background, can minimize)
   - SEL Discord Bot (main window)

7. **That's it!** SEL is running.

**Pros**:
- Fast and reliable
- Easy to update
- Traditional Windows workflow

**Cons**:
- Requires Python pre-installed

---

### Method 3: Manual Installation (Advanced) ⭐⭐⭐

**Best for**: Developers, advanced users, troubleshooting

**Prerequisites**:
- Python 3.11+ with pip
- Git (optional, for cloning)

**Steps**:

1. **Clone or download** the repository

2. **Open PowerShell** in the repository folder

3. **Install Poetry** (if not already installed):
   ```powershell
   (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
   ```

4. **Add Poetry to PATH**:
   - Add `%APPDATA%\Python\Scripts` to your PATH
   - Restart PowerShell

5. **Navigate to project_echo**:
   ```powershell
   cd project_echo
   ```

6. **Configure Poetry**:
   ```powershell
   poetry config virtualenvs.in-project true
   ```

7. **Install dependencies**:
   ```powershell
   poetry install
   ```
   (This takes 5-10 minutes)

8. **Create and configure .env**:
   ```powershell
   cd ..
   copy .env.example .env
   notepad .env
   ```
   Add your tokens and save.

9. **Start HIM service** (Terminal 1):
   ```powershell
   cd project_echo
   poetry run python run_him.py --data-dir ./data --host 127.0.0.1 --port 8000
   ```

10. **Start Discord bot** (Terminal 2):
    ```powershell
    cd project_echo
    poetry run python -m sel_bot.main
    ```

11. **SEL is running!**

**Pros**:
- Full control
- Easy debugging
- Best for development

**Cons**:
- More complex
- Manual service management

---

## 🔑 Getting Your Tokens

### Discord Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Name it (e.g., "SEL Bot")
4. Go to "Bot" tab
5. Click "Reset Token" → Copy the token
6. **Enable Privileged Gateway Intents**:
   - ✅ Presence Intent
   - ✅ Server Members Intent  
   - ✅ Message Content Intent
7. Go to OAuth2 → URL Generator
8. Select scopes:
   - `bot`
9. Select bot permissions:
   - Read Messages/View Channels
   - Send Messages
   - Read Message History
10. Copy generated URL
11. Open URL in browser to invite bot to your server

### OpenRouter API Key

1. Go to [OpenRouter](https://openrouter.ai/)
2. Sign up or log in
3. Go to [Keys section](https://openrouter.ai/keys)
4. Click "Create Key"
5. Name it (e.g., "SEL Bot")
6. Copy the key (starts with `sk-or-v1-...`)

---

## ⚙️ Configuration

Edit `.env` to customize SEL:

### Required Settings
```env
DISCORD_BOT_TOKEN=your_discord_token_here
OPENROUTER_API_KEY=your_openrouter_key_here
```

### Optional Settings
```env
# AI Models
OPENROUTER_MAIN_MODEL=anthropic/claude-3.5-sonnet
OPENROUTER_UTIL_MODEL=anthropic/claude-3-haiku-20240307
OPENROUTER_MAIN_TEMP=0.8

# Database (default is SQLite)
DATABASE_URL=sqlite+aiosqlite:///./sel.db

# HIM Memory Service
HIM_ENABLED=1
HIM_PORT=8000

# Bot Behavior
SEL_PERSONA_SEED=You are Sel, a playful Discord assistant
INACTIVITY_PING_HOURS=48.0
```

See `WINDOWS_SETUP.md` for all configuration options.

---

## ✅ Verification

After installation:

1. **Check console output** for errors
2. **Go to Discord** and mention your bot
3. **Test interaction**: Send a message
4. **Verify response**: Bot should reply
5. **Check HIM service**: Should show activity in its window

---

## ❓ Troubleshooting

### Installation Issues

#### "Python not found"
- Install Python 3.11+ from https://www.python.org/downloads/
- During installation, check ☑️ "Add Python to PATH"
- Restart terminal after installation

#### "Poetry not found"
- Run `install_sel.ps1` again
- Or install manually: `(Invoke-WebRequest -Uri https://install.python-poetry.org).Content | python -`
- Add `%APPDATA%\Python\Scripts` to PATH
- Restart terminal

#### "PowerShell script won't run"
- Open PowerShell as Administrator
- Run: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`
- Try again

#### "ModuleNotFoundError"
```powershell
cd project_echo
poetry install --no-cache
```

### Runtime Issues

#### "Bot doesn't respond"
- ✅ Check `.env` has correct tokens
- ✅ Verify Discord bot permissions
- ✅ Ensure Message Content Intent is enabled
- ✅ Check bot is online in Discord
- ✅ Look for errors in console

#### "Port already in use"
- Change port in `.env`: `HIM_PORT=8001`
- Or find and stop the other process

#### "Connection refused to HIM service"
- Check HIM service window for errors
- Verify `HIM_PORT` matches in both services
- Try disabling HIM temporarily: `HIM_ENABLED=0`

#### "Memory errors or crashes"
- Check available RAM (need 2GB+)
- Reduce context limits in `.env`
- Restart the bot

### Getting More Help

1. Check `WINDOWS_SETUP.md` for detailed troubleshooting
2. Review console logs for error messages
3. Run `check_system.bat` to verify system state
4. Check GitHub issues for similar problems
5. Join support Discord (if available)

---

## 🔄 Updating SEL

To update to the latest version:

### If using Git:
```powershell
git pull origin main
cd project_echo
poetry install
```

### If using ZIP download:
1. Download latest version
2. Extract to new folder
3. Copy your `.env` file from old folder
4. Copy `data/` directory (if you want to keep memories)
5. Run `install_sel.ps1` in new folder

---

## 🗑️ Uninstalling

To remove SEL:

1. **Stop the bot** (Ctrl+C or close windows)
2. **Delete the SEL folder**
3. **(Optional) Remove Poetry**:
   ```powershell
   (Invoke-WebRequest -Uri https://install.python-poetry.org).Content | python - --uninstall
   ```

---

## 📚 Next Steps

Once SEL is running:

- 💬 **Start chatting** with the bot in Discord
- 🧠 **Build memory** - SEL remembers conversations
- 🎭 **Watch personality develop** - Emotional states evolve
- ⚙️ **Try system commands** (if authorized)
- 📖 **Read the docs** - See `CLAUDE.md` for details

---

## 🎯 Quick Command Reference

| Action | Command |
|--------|---------|
| Check system | `check_system.bat` |
| Install | `install_sel.ps1` |
| Start SEL | `start_sel.bat` |
| Build exe | `build_windows_exe.bat` |
| Manual bot start | `cd project_echo && poetry run python -m sel_bot.main` |
| Manual HIM start | `cd project_echo && poetry run python run_him.py --data-dir ./data` |
| Run tests | `cd project_echo && poetry run pytest` |

---

## 📖 Additional Documentation

- **Quick Start**: `WINDOWS_README.md`
- **Detailed Setup**: `WINDOWS_SETUP.md`
- **Quick Reference**: `WINDOWS_QUICK_REF.md`
- **Building Executable**: `BUILDING_WINDOWS_EXE.md`
- **Implementation Details**: `WINDOWS_IMPLEMENTATION.md`
- **Developer Guide**: `CLAUDE.md`
- **Main README**: `README.md`

---

## 🤝 Support

For help:
- 📧 Check documentation files
- 🐛 GitHub Issues
- 💬 Discord support (if available)
- 📝 Review console logs

---

**Enjoy using SEL!** 🤖

---

*Last updated: December 2025*
