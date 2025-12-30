# 🪟 Windows Support for SEL - Start Here

SEL now has **full Windows support** with multiple installation options!

## 🎯 Choose Your Path

### 👤 I'm a User (Just want to run SEL)
→ **Start here**: [`WINDOWS_INSTALL.md`](WINDOWS_INSTALL.md)
- Complete step-by-step guide
- Multiple installation methods
- Troubleshooting included

**Quick version**: [`WINDOWS_README.md`](WINDOWS_README.md)

### 👨‍💻 I'm a Developer (Want to contribute/customize)
→ **Start here**: [`WINDOWS_QUICK_REF.md`](WINDOWS_QUICK_REF.md)
- Quick command reference
- Development workflow
- Testing and debugging

**Detailed setup**: [`WINDOWS_SETUP.md`](WINDOWS_SETUP.md)

### 📦 I Want to Distribute SEL
→ **Start here**: [`BUILDING_WINDOWS_EXE.md`](BUILDING_WINDOWS_EXE.md)
- How to build the executable
- Packaging for distribution
- Testing and signing

**Implementation details**: [`WINDOWS_IMPLEMENTATION.md`](WINDOWS_IMPLEMENTATION.md)

---

## 🚀 Quick Start (TL;DR)

### Absolute Fastest Way:

1. **Install Python 3.11+** → https://www.python.org/downloads/
   - ✅ Check "Add Python to PATH"

2. **Run installer**:
   ```
   Right-click install_sel.ps1 → Run with PowerShell
   ```

3. **Edit `.env`** with your tokens

4. **Start SEL**:
   ```
   Double-click start_sel.bat
   ```

Done! 🎉

---

## 📁 What's What?

### To Install & Run:
- `install_sel.ps1` - Run this first
- `start_sel.bat` - Run this to start SEL
- `check_system.bat` - (Optional) Check if your system is ready

### For Building Executable:
- `windows_launcher.py` - Source code
- `sel_windows.spec` - Build configuration
- `build_windows_exe.bat` - Build script

### Documentation:
- `WINDOWS_INSTALL.md` - **👈 Start here for full guide**
- `WINDOWS_README.md` - Simplified user guide
- `WINDOWS_SETUP.md` - Detailed setup & troubleshooting
- `WINDOWS_QUICK_REF.md` - Command reference
- `BUILDING_WINDOWS_EXE.md` - Building executable
- `WINDOWS_IMPLEMENTATION.md` - Technical details

---

## ❓ Common Questions

### Do I need the executable?
**No.** You can use the PowerShell scripts instead. The executable is just a convenience wrapper.

### Can I use Docker on Windows?
**Yes.** Install Docker Desktop and use WSL2 backend. See [`WINDOWS_SETUP.md`](WINDOWS_SETUP.md) for details.

### Will the system agent work?
**Partially.** Some Unix commands won't work. For full functionality, use WSL2. See [`WINDOWS_SETUP.md`](WINDOWS_SETUP.md).

### How do I update SEL?
```powershell
git pull
cd project_echo
poetry install
```
Or download the new version and copy your `.env` and `data/` folder.

### How do I uninstall?
Just delete the SEL folder. Optionally uninstall Poetry if you don't need it.

---

## 🆘 Help!

### Something's not working
1. Check [`WINDOWS_SETUP.md`](WINDOWS_SETUP.md) troubleshooting section
2. Run `check_system.bat` to diagnose
3. Review console error messages
4. Check GitHub issues

### I need step-by-step instructions
Go to [`WINDOWS_INSTALL.md`](WINDOWS_INSTALL.md) - it has detailed steps for all methods

### I'm getting Python errors
Make sure Python 3.11+ is installed and in PATH:
```powershell
python --version
```

### I'm getting Poetry errors
Run the installer again:
```powershell
.\install_sel.ps1
```

---

## 🎓 Learning Path

1. **First time?** → [`WINDOWS_INSTALL.md`](WINDOWS_INSTALL.md)
2. **Need quick reference?** → [`WINDOWS_QUICK_REF.md`](WINDOWS_QUICK_REF.md)
3. **Want to understand how it works?** → [`WINDOWS_IMPLEMENTATION.md`](WINDOWS_IMPLEMENTATION.md)
4. **Want to distribute?** → [`BUILDING_WINDOWS_EXE.md`](BUILDING_WINDOWS_EXE.md)
5. **Want to develop?** → [`CLAUDE.md`](CLAUDE.md)

---

## 🎯 File Decision Tree

```
Are you...

├─ Just wanting to USE SEL?
│  └─→ WINDOWS_INSTALL.md (Installation guide)
│
├─ Having PROBLEMS?
│  └─→ WINDOWS_SETUP.md (Detailed troubleshooting)
│
├─ Need QUICK commands?
│  └─→ WINDOWS_QUICK_REF.md (Command reference)
│
├─ Want to BUILD executable?
│  └─→ BUILDING_WINDOWS_EXE.md (Build guide)
│
├─ Want to UNDERSTAND implementation?
│  └─→ WINDOWS_IMPLEMENTATION.md (Technical details)
│
└─ Need SIMPLE instructions?
   └─→ WINDOWS_README.md (Beginner guide)
```

---

## ✅ Checklist

- [ ] Python 3.11+ installed with PATH
- [ ] Downloaded/cloned SEL repository
- [ ] Ran `install_sel.ps1`
- [ ] Created `.env` with Discord and OpenRouter tokens
- [ ] Invited bot to Discord server
- [ ] Ran `start_sel.bat`
- [ ] Bot responds in Discord

If all checked: **You're done!** 🎉

If stuck: See [`WINDOWS_SETUP.md`](WINDOWS_SETUP.md) troubleshooting

---

## 📚 Complete File List

**Installation Scripts:**
- `install_sel.ps1` - PowerShell installer
- `start_sel.bat` - Launcher
- `check_system.bat` - System checker
- `build_windows_exe.bat` - Executable builder
- `windows_launcher.py` - Launcher source
- `sel_windows.spec` - PyInstaller config

**Documentation:**
- `WINDOWS_START_HERE.md` - This file
- `WINDOWS_INSTALL.md` - Installation guide ⭐
- `WINDOWS_README.md` - Simple user guide
- `WINDOWS_SETUP.md` - Detailed setup
- `WINDOWS_QUICK_REF.md` - Quick reference
- `BUILDING_WINDOWS_EXE.md` - Build guide
- `WINDOWS_IMPLEMENTATION.md` - Technical docs
- `WINDOWS_FILES_SUMMARY.txt` - File summary

---

**Ready to start?** → [`WINDOWS_INSTALL.md`](WINDOWS_INSTALL.md)

**Need help?** → [`WINDOWS_SETUP.md`](WINDOWS_SETUP.md)

**Quick commands?** → [`WINDOWS_QUICK_REF.md`](WINDOWS_QUICK_REF.md)

---

*Enjoy using SEL on Windows!* 🪟🤖
