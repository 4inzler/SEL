# 🪟 SEL for Windows - Quick Start

Welcome! This is the simplified guide for running SEL on Windows.

## What is SEL?

SEL is an intelligent Discord bot that:
- Remembers conversations and builds context over time
- Has emotional states that influence responses
- Can execute system commands (if authorized)
- Uses hierarchical memory for long-term retention

## 🚀 Fastest Way to Start

### Step 1: Get Python
1. Download [Python 3.11+](https://www.python.org/downloads/)
2. **Important**: Check "Add Python to PATH" during installation
3. Verify: Open Command Prompt and type `python --version`

### Step 2: Install SEL
Double-click **`install_sel.ps1`**

(Or right-click → "Run with PowerShell")

This will:
- Install Poetry (Python package manager)
- Download all dependencies
- Set up the environment

### Step 3: Configure Tokens
1. Open **`.env`** in Notepad
2. Add your tokens:
   ```
   DISCORD_BOT_TOKEN=your_bot_token_here
   OPENROUTER_API_KEY=your_openrouter_key_here
   ```
3. Save and close

**Don't have tokens?** See "Getting Tokens" below.

### Step 4: Start SEL
Double-click **`start_sel.bat`**

Two windows will open:
- **HIM Service** (background memory system)
- **SEL Bot** (main Discord bot)

That's it! SEL is now running. 🎉

## 🔑 Getting Tokens

### Discord Bot Token
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Go to "Bot" tab → "Reset Token" → Copy
4. Enable these under "Privileged Gateway Intents":
   - Message Content Intent ✓
   - Server Members Intent ✓
   - Presence Intent ✓
5. Go to OAuth2 → URL Generator
6. Select: `bot` scope
7. Permissions: "Send Messages", "Read Messages", "Read Message History"
8. Copy URL and invite bot to your server

### OpenRouter API Key
1. Go to [OpenRouter.ai](https://openrouter.ai/)
2. Sign up / Log in
3. Go to [Keys](https://openrouter.ai/keys)
4. Create new key → Copy

## 📦 Alternative: Use the Executable

If available, you can use **`sel_launcher.exe`** instead:
- Just double-click it
- It handles installation automatically
- Guides you through setup

## ⚙️ Configuration

Edit **`.env`** to customize SEL:

```env
# Required
DISCORD_BOT_TOKEN=your_token
OPENROUTER_API_KEY=your_key

# Optional: Change AI models
OPENROUTER_MAIN_MODEL=anthropic/claude-3.5-sonnet
OPENROUTER_UTIL_MODEL=anthropic/claude-3-haiku-20240307

# Optional: Database (default is SQLite)
DATABASE_URL=sqlite+aiosqlite:///./sel.db

# Optional: Personality
SEL_PERSONA_SEED=You are Sel, a playful Discord assistant
```

## 🛑 Stopping SEL

Press **Ctrl+C** in the bot window, or just close the windows.

## ❓ Troubleshooting

### "Python not found"
- Reinstall Python with "Add to PATH" checked
- Or manually add Python to Windows PATH

### "Poetry not found"
- Run `install_sel.ps1` again
- Or install manually: `(Invoke-WebRequest -Uri https://install.python-poetry.org).Content | python -`

### Bot doesn't respond
- Check `.env` has correct tokens
- Verify bot has permissions in Discord
- Check Message Content Intent is enabled

### Port already in use
Change HIM port in `.env`:
```env
HIM_PORT=8001
```

### Need more help?
See **`WINDOWS_SETUP.md`** for detailed troubleshooting.

## 📁 What's What?

```
Your SEL Folder/
├── sel_launcher.exe      ← All-in-one launcher (if you have it)
├── start_sel.bat         ← Start SEL (after install)
├── install_sel.ps1       ← Install dependencies
├── .env                  ← Your configuration (tokens go here)
├── .env.example          ← Template for .env
├── project_echo/         ← The actual bot code
│   ├── sel_bot/          ← Discord bot
│   ├── him/              ← Memory system
│   └── data/             ← Where memories are stored
└── agents/               ← Optional system agents
```

## 🎯 Next Steps

Once SEL is running:
1. Go to Discord and message your bot
2. Have a conversation - SEL will remember!
3. SEL's personality develops over time
4. Check console output to see what SEL is thinking

## 🔧 Advanced Features

- **System Commands**: Authorized users can ask SEL to run commands
- **Memory Backfill**: Import old conversations from Discord history
- **Custom Agents**: Add new capabilities by dropping Python files in `/agents`
- **Docker**: Run in container for better isolation

See main **`README.md`** and **`CLAUDE.md`** for developer info.

## 📝 License

See `LICENSE.md` for details.

---

**Enjoy using SEL!** 🤖

For detailed documentation: [WINDOWS_SETUP.md](WINDOWS_SETUP.md)
