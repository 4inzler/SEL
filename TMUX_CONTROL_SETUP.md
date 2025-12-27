# Tmux Terminal Control for SEL

This system allows SEL to control persistent terminal sessions via tmux, enabling:
- Multi-step command workflows
- Interactive session management
- Parallel command execution in different sessions
- Output capture and analysis

---

## 🚀 Quick Setup

### 1. Install tmux

```bash
# Ubuntu/Debian
sudo apt install tmux

# macOS
brew install tmux

# Arch Linux
sudo pacman -S tmux
```

### 2. Generate Authentication Token

```bash
# Generate a secure token
python3 -c "import secrets; print(secrets.token_hex(32))"

# Example output:
# 7a9f2e1d4c8b6a3e5f9d2c7b1a4e8f3c6d9b2e5a8c1f4d7b0e3a6c9f2e5d8b1
```

### 3. Configure Environment

Add to your `.env` file:

```bash
# Tmux Control
TMUX_CONTROL_TOKEN=7a9f2e1d4c8b6a3e5f9d2c7b1a4e8f3c6d9b2e5a8c1f4d7b0e3a6c9f2e5d8b1
TMUX_CONTROL_URL=http://localhost:9001
```

For Docker, add to `docker-compose.yml`:

```yaml
services:
  sel-service:
    environment:
      - TMUX_CONTROL_TOKEN=7a9f2e1d4c8b6a3e5f9d2c7b1a4e8f3c6d9b2e5a8c1f4d7b0e3a6c9f2e5d8b1
      - TMUX_CONTROL_URL=http://host.docker.internal:9001
```

### 4. Start the Tmux Control API

```bash
# Set the token
export TMUX_CONTROL_TOKEN=7a9f2e1d4c8b6a3e5f9d2c7b1a4e8f3c6d9b2e5a8c1f4d7b0e3a6c9f2e5d8b1

# Run the server
python3 tmux_control_api.py
```

You should see:
```
Tmux Control API listening on http://0.0.0.0:9001
Available endpoints:
  POST   /sessions        - Create new session
  GET    /sessions        - List all sessions
  GET    /sessions/{name} - Get session output
  DELETE /sessions/{name} - Kill session
  POST   /execute         - Execute command
  POST   /capture         - Capture output
```

---

## 💬 Using Tmux Control in Discord

SEL can now execute commands in persistent terminal sessions!

### Basic Commands

**Execute a single command:**
```
Sel, run ls -la
Sel, execute pwd
```

**Multi-line commands:**
```
Sel, run cd /tmp && cat test.txt
```

**View output:**
```
Sel, show output
Sel, show output from dev
```

### Session Management

**Create named sessions:**
```
Sel, create session dev
Sel, new session build
```

**Execute in specific session:**
```
Sel, run npm install in session dev
Sel, execute python script.py in session build wait 5000
```

**List sessions:**
```
Sel, list sessions
Sel, show sessions
```

**Kill sessions:**
```
Sel, kill session dev
Sel, close session build
```

### Example Workflows

**Development workflow:**
```
User: Sel, create session backend
Sel: ✅ Created tmux session: backend

User: Sel, run cd ~/projects/api && npm install in session backend
Sel: ✅ Executed in tmux session 'backend':
Command: `cd ~/projects/api && npm install`
Output:
```
added 234 packages in 12s
```

User: Sel, run npm start in session backend
Sel: ✅ Executed in tmux session 'backend':
(No output captured - command may still be running)

User: Sel, show output from backend
Sel: 📋 Output from 'backend':
```
Server listening on http://localhost:3000
```
```

**Parallel execution:**
```
User: Sel, create session frontend
User: Sel, create session backend
User: Sel, run npm start in session frontend
User: Sel, run python app.py in session backend
User: Sel, list sessions

Sel: 📺 Active tmux sessions:
  • frontend (2 commands executed)
  • backend (3 commands executed)
  • sel-main (0 commands executed)
```

**Long-running commands:**
```
User: Sel, run find / -name "*.log" wait 5000 in session search
Sel: ✅ Executed in tmux session 'search':
Command: `find / -name "*.log"`
Output:
(last 30 lines shown)
```

---

## 🔧 API Endpoints

### POST /execute
Execute command in tmux session.

```bash
curl -X POST http://localhost:9001/execute \
  -H "Content-Type: application/json" \
  -H "X-Tmux-Token: YOUR_TOKEN" \
  -d '{
    "command": "ls -la",
    "session": "sel-main",
    "capture_output": true,
    "wait_ms": 1000
  }'
```

Response:
```json
{
  "status": "executed",
  "session": "sel-main",
  "command": "ls -la",
  "output": "total 48\ndrwxr-xr-x  8 user  staff   256 Dec 11 00:00 .\n..."
}
```

### GET /sessions
List all active sessions.

```bash
curl http://localhost:9001/sessions \
  -H "X-Tmux-Token: YOUR_TOKEN"
```

Response:
```json
{
  "sessions": [
    {
      "name": "sel-main",
      "created_at": 1702252800.0,
      "command_count": 5,
      "last_command_at": 1702252900.0
    }
  ]
}
```

### GET /sessions/{name}
Get recent output from session.

```bash
curl http://localhost:9001/sessions/sel-main \
  -H "X-Tmux-Token: YOUR_TOKEN"
```

### POST /sessions
Create new session.

```bash
curl -X POST http://localhost:9001/sessions \
  -H "Content-Type: application/json" \
  -H "X-Tmux-Token: YOUR_TOKEN" \
  -d '{"session_name": "dev"}'
```

### DELETE /sessions/{name}
Kill a session.

```bash
curl -X DELETE http://localhost:9001/sessions/dev \
  -H "X-Tmux-Token: YOUR_TOKEN"
```

---

## 🔒 Security Considerations

### Token Security
- **Never commit tokens** to version control
- Use strong, randomly generated tokens (32+ characters)
- Store in `.env` file (gitignored)
- Rotate tokens regularly

### Network Security
- Bind to `127.0.0.1` instead of `0.0.0.0` if not using Docker:
  ```python
  # In tmux_control_api.py, change:
  HOST = "127.0.0.1"
  ```

### Command Safety
- Tmux sessions run with your user privileges
- Be careful with destructive commands
- Consider running in a restricted user account
- Monitor session activity via logs

### Docker Considerations
- Use `http://host.docker.internal:9001` for TMUX_CONTROL_URL
- Ensure token is passed securely via environment
- Consider volume mounts for file access

---

## 🐛 Troubleshooting

### Error: "tmux is not installed"
```bash
# Install tmux
sudo apt install tmux  # Ubuntu/Debian
brew install tmux      # macOS
```

### Error: "TMUX_CONTROL_TOKEN not configured"
```bash
# Check token is set
echo $TMUX_CONTROL_TOKEN

# If empty, export it:
export TMUX_CONTROL_TOKEN=your_token_here
```

### Error: "Connection refused"
- Ensure tmux_control_api.py is running
- Check port 9001 is not blocked by firewall
- For Docker, use `host.docker.internal` instead of `localhost`

### Commands not producing output
- Increase `wait_ms` parameter (default 1000ms may be too short)
- Some commands (like `npm start`) run continuously and don't produce immediate output
- Use "show output" later to see accumulated output

### Session not found
```bash
# List tmux sessions directly:
tmux list-sessions

# Attach to session to debug:
tmux attach -t sel-main
```

---

## 📊 Comparison: Tmux Control vs Host Exec

| Feature | Tmux Control | Host Exec |
|---------|--------------|-----------|
| **Execution Model** | Persistent sessions | One-off commands |
| **State** | Maintains shell state | Stateless |
| **Multi-step** | ✅ Yes (cd, env vars persist) | ❌ No |
| **Interactive** | ✅ Yes | ❌ No |
| **Output Capture** | Async (capture later) | Immediate |
| **Parallel Execution** | ✅ Multiple sessions | ❌ Sequential |
| **Use Case** | Development workflows | Quick system info |
| **Port** | 9001 | 9000 |

---

## 🎯 Use Cases

### Development Servers
```
Sel, create session backend
Sel, run cd ~/api && npm start in session backend
# Server runs persistently in background
Sel, show output from backend  # Check status later
```

### Long-Running Tasks
```
Sel, create session build
Sel, run ./build.sh in session build wait 10000
# Build runs while you do other things
```

### Multi-Step Workflows
```
Sel, create session deploy
Sel, run cd /var/www in session deploy
Sel, run git pull in session deploy
Sel, run npm install in session deploy
Sel, run pm2 restart all in session deploy
```

### Debugging
```
Sel, create session debug
Sel, run tail -f /var/log/app.log in session debug
# Watch logs in real-time
Sel, show output from debug
```

---

## 🔮 Advanced Features

### Custom Wait Times
For slow commands, increase wait time:
```
Sel, run npm install wait 5000
# Waits 5 seconds before capturing output
```

### Output Monitoring
```
# Start long-running command
Sel, run ./train_model.py in session ml

# Check progress periodically
Sel, show output from ml
Sel, show output from ml  # Check again later
```

### Session Cleanup
```
# List what's running
Sel, list sessions

# Kill unused sessions
Sel, kill session old-session
```

---

## 📝 Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TMUX_CONTROL_TOKEN` | (required) | Authentication token |
| `TMUX_CONTROL_URL` | `http://localhost:9001` | API endpoint |

### API Configuration

Edit `tmux_control_api.py` to change:
- `HOST`: Bind address (default: `0.0.0.0`)
- `PORT`: Listen port (default: `9001`)
- `DEFAULT_SESSION`: Default session name (default: `sel-main`)

---

## ✅ Verification

Test the complete setup:

```bash
# 1. Start API server
export TMUX_CONTROL_TOKEN=test123
python3 tmux_control_api.py &

# 2. Test via curl
curl -X POST http://localhost:9001/execute \
  -H "X-Tmux-Token: test123" \
  -d '{"command": "echo Hello from tmux"}'

# 3. Check tmux session
tmux list-sessions
tmux attach -t sel-main  # Press Ctrl+B, D to detach

# 4. In Discord, tell Sel:
"Sel, run echo Testing tmux control"
```

If all steps work, you're ready to go! 🎉
