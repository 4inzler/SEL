# SEL Selfbot (Rust)

⚠️ **WARNING**: Using selfbots violates [Discord's Terms of Service](https://discord.com/terms) and can result in account termination. This project is for educational purposes only.

A Rust implementation of SEL (Self-Evolving Learner) that runs as a Discord user account instead of a bot account. This version mirrors all functionality from the Python Discord bot implementation.

## Features

All features from the original SEL Discord bot:

- **Hierarchical Image Memory (HIM)**: Episodic memory system with vector-based retrieval
- **Hormone System**: Emotional state tracking (dopamine, serotonin, cortisol, etc.)
- **LLM Integration**: OpenRouter API with Claude/GPT models
- **Agent System**: Pluggable agents for extended capabilities
  - `system_agent`: Terminal/system commands
  - `browser`: Web search and content extraction
  - `image_gen`: AI image generation via SwarmUI
- **Presence Tracking**: Monitor Discord user status and activities
- **Context Awareness**: Time, weather, and conversation history
- **Natural Conversation**: Genuine interactions with memory and emotional state
- **Voice Channel Support**: Join voice channels and speak responses using ElevenLabs TTS
- **Speech-to-Text (STT)**: Listen to voice and respond to spoken messages
- **Auto Voice Responses**: Automatically speaks in voice when connected
- **Voice Conversations**: Full two-way voice interaction (listen + speak)

## Voice Channel Features

SEL can join Discord voice channels for full voice interaction using ElevenLabs:

**Commands:**
- `sel join vc` or `sel join voice` - Join your current voice channel
- `sel leave vc` or `sel leave voice` - Leave voice channel

**Voice Capabilities:**
- **Text-to-Speech (TTS)**: Speaks all responses using ElevenLabs voices
- **Speech-to-Text (STT)**: Listens to and transcribes voice messages
- **Two-Way Conversation**: Speak to SEL and get voice responses back
- **Auto-Detection**: Automatically detects when users start/stop speaking
- **Natural Speech**: High-quality, natural-sounding synthesis and transcription

**Behavior:**
- When in a voice channel, SEL automatically speaks all responses using TTS
- SEL listens to voice and transcribes it to text automatically
- Responds to both text and voice messages
- Text responses still appear in chat alongside voice
- Configurable voice, model, and speech parameters

## Why Rust?

- **Performance**: Faster startup and lower memory usage
- **Reliability**: Strong type system prevents many runtime errors
- **Async**: Native async/await for non-blocking Discord operations
- **Safety**: Memory safety without garbage collection

## Requirements

1. **Rust 1.70+** - [Install Rust](https://rustup.rs/)
2. **Discord User Account** - You'll need your user token (see below)
3. **OpenRouter API Key** - For LLM access
4. **ElevenLabs API Key** - For voice TTS (optional, for voice features)
5. **Python 3.11+** - For running Python-based agents (optional but recommended)

## Installation

### 1. Clone and Setup

```bash
cd sel_selfbot_rust
cp selfbot.env.example selfbot.env
```

### 2. Get Your Discord User Token

⚠️ **DANGER**: Never share your user token! It gives full access to your account.

**Method 1: Browser Developer Tools**
1. Open Discord in your browser (discord.com)
2. Press F12 to open DevTools
3. Go to Network tab
4. Reload the page
5. Look for any request to `discord.com/api`
6. Check the Request Headers for `authorization`
7. Copy the token (it's a long string)

**Method 2: Discord Desktop App**
1. Press Ctrl+Shift+I (Windows) or Cmd+Opt+I (Mac)
2. Go to Console tab
3. Paste: `(webpackChunkdiscord_app.push([[''],{},e=>{m=[];for(let c in e.c)m.push(e.c[c])}]),m).find(m=>m?.exports?.default?.getToken!==void 0).exports.default.getToken()`
4. Press Enter
5. Copy the token

### 3. Configure `selfbot.env`

Edit `selfbot.env` and set:
```env
DISCORD_USER_TOKEN=your_token_here
OPENROUTER_API_KEY=your_openrouter_key_here
```

### 4. Build and Run

```bash
# Build
cargo build --release

# Run
cargo run --release
```

Or use development mode (faster compile, slower runtime):
```bash
cargo run
```

## Configuration

See `selfbot.env.example` for all configuration options. Key settings:

- `DISCORD_USER_TOKEN`: Your Discord user token (REQUIRED)
- `OPENROUTER_API_KEY`: OpenRouter API key (REQUIRED)
- `OPENROUTER_MAIN_MODEL`: Main conversation model (default: claude-3.5-sonnet)
- `APPROVAL_USER_ID`: Discord user ID authorized for system commands
- `WHITELIST_CHANNEL_IDS`: Comma-separated channel IDs (empty = all channels)
- `HIM_API_BASE_URL`: HIM memory service endpoint
- `AGENTS_DIR`: Path to Python agents directory
- `ELEVENLABS_API_KEY`: ElevenLabs API key for voice TTS (optional)
- `ELEVENLABS_VOICE_ID`: Voice ID to use (default: Rachel)

### Voice Configuration

To enable voice support (TTS + STT):

1. Sign up at [ElevenLabs](https://elevenlabs.io/)
2. Get your API key from the profile page
3. Add to `selfbot.env`:
```env
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # Rachel (default)

# Enable/disable STT
STT_ENABLED=true
ELEVENLABS_STT_MODEL=eleven_multilingual_v2
```

**TTS Parameters:**
- `ELEVENLABS_MODEL`: TTS model (default: `eleven_monolingual_v1`)
- `ELEVENLABS_STABILITY`: Voice stability 0.0-1.0 (default: 0.5)
- `ELEVENLABS_SIMILARITY`: Similarity boost 0.0-1.0 (default: 0.75)
- `ELEVENLABS_STYLE`: Style exaggeration 0.0-1.0 (default: 0.0)
- `ELEVENLABS_VOICE_ID`: Voice to use (browse at https://elevenlabs.io/voice-library)

**STT Parameters:**
- `STT_ENABLED`: Enable/disable voice listening (default: `true`)
- `ELEVENLABS_STT_MODEL`: STT model (default: `eleven_multilingual_v2`)

**Note:** Both TTS and STT use the same ElevenLabs API key!

## Usage

Once running, SEL will respond to messages in Discord channels:

### Natural Conversation
```
You: hey sel, what's the weather like?
SEL: I don't have weather info right now, but I can check if you want!
```

### Agent Invocation
```
You: agent:system_agent disk space
SEL: [system_agent output showing disk usage]

You: agent:image_gen a sunset over the ocean
SEL: ✨ Generated image: a sunset over the ocean
     [Image attachment]

You: agent:browser search rust async programming
SEL: [Search results with links and snippets]
```

### Automatic System Detection
For approved users, SEL can detect system queries:
```
You: what's running on port 8000?
SEL: [Automatically invokes system_agent to check]
```

### Voice Channel Usage
Join a voice channel and have full voice conversations with SEL:

**Text-based control:**
```
You (text): sel join vc
SEL: Joined voice channel! 🎤

You (text): tell me about rust
SEL: [Types response in text AND speaks it in voice]
```

**Voice-based interaction:**
```
You (voice): "Hey SEL, what's the weather like?"
SEL (voice + text): [Transcribes your voice, responds in both voice and text]

You (voice): "Tell me a joke"
SEL (voice + text): [Hears you, responds with a joke in voice]
```

**Leaving:**
```
You: sel leave vc
SEL: Left voice channel
```

**Voice behavior:**
- SEL **listens** to all voice and transcribes it automatically
- SEL **speaks** all responses when in voice
- Text responses still appear in chat alongside voice
- Uses ElevenLabs for both STT (listening) and TTS (speaking)
- Automatically detects when you start/stop speaking
- Automatically finds your voice channel when you say "join vc"

## Agents

SEL uses the same agent system as the Python version. Python agents in `./agents/` are called via subprocess.

### Available Agents

- **system_agent**: Terminal commands, disk space, processes, ports
- **browser**: Web search via Playwright, URL fetching
- **image_gen**: AI image generation via SwarmUI

### Adding Custom Agents

Create Python files in `./agents/`:

```python
"""My Custom Agent"""

DESCRIPTION = "Does something cool"

def run(query: str, **kwargs) -> str:
    # Your logic here
    return "result"
```

## Memory System

SEL uses the HIM (Hierarchical Image Memory) API for episodic memory:

1. Start the HIM service (from Python version):
```bash
cd project_echo
poetry run python run_him.py
```

2. SEL will automatically store and retrieve memories
3. Memories influence responses and emotional state

## Hormone System

SEL tracks emotional state through hormones:

- **dopamine**: Reward, engagement
- **serotonin**: Well-being, contentment
- **oxytocin**: Bonding, trust
- **cortisol**: Stress, urgency
- **melatonin**: Rest, reduced activity
- **novelty**: Exposure to new stimuli
- **curiosity**: Drive to explore
- **patience**: Tolerance for delays

These decay over time and are updated based on interactions.

## Safety Notes

### Discord TOS Violation

Using selfbots violates Discord's Terms of Service:
- Your account can be permanently banned
- There is no appeal process
- Use at your own risk

### Best Practices

1. **Don't spam**: Rate-limit your responses
2. **Don't automate**: Manual use only
3. **Don't share your token**: Keep it secret
4. **Use an alt account**: Don't risk your main account
5. **Monitor usage**: Watch for unusual activity

### Token Security

- Never commit `selfbot.env` to git
- Rotate your token if leaked
- Use environment variables in production
- Don't share logs containing tokens

## Troubleshooting

### "Failed to connect to Discord"
- Check your token is valid
- Ensure you're not behind a restrictive firewall
- Try regenerating your token

### "OpenRouter API error"
- Verify your API key is correct
- Check you have credits/billing set up
- Review rate limits

### "Agent execution failed"
- Ensure Python is installed for Python agents
- Check the agent file exists in `AGENTS_DIR`
- Review agent-specific error messages

### "HIM API unavailable"
- Memory features will be disabled but SEL will still work
- Start the HIM service from the Python version
- Check `HIM_API_BASE_URL` is correct

## Development

### Project Structure

```
sel_selfbot_rust/
├── src/
│   ├── main.rs           # Entry point, event handler
│   ├── config.rs         # Configuration loading
│   ├── llm_client.rs     # OpenRouter LLM client
│   ├── memory.rs         # HIM memory integration
│   ├── hormones.rs       # Emotional state tracking
│   ├── presence.rs       # Discord presence tracking
│   ├── agents.rs         # Agent execution
│   └── prompts.rs        # System prompt building
├── Cargo.toml            # Dependencies
├── .env.example          # Example configuration
└── README.md             # This file
```

### Building

```bash
# Debug build (fast compile, slow runtime)
cargo build

# Release build (slow compile, fast runtime)
cargo build --release

# Run tests
cargo test

# Check code without building
cargo check

# Format code
cargo fmt

# Lint code
cargo clippy
```

### Logging

Set log level via `RUST_LOG`:

```bash
# Info level (default)
RUST_LOG=info cargo run

# Debug level
RUST_LOG=debug cargo run

# Trace level (very verbose)
RUST_LOG=trace cargo run
```

## Comparison to Python Version

| Feature | Python Bot | Rust Selfbot |
|---------|-----------|--------------|
| Discord API | discord.py (bot) | discord-selfbot (user) |
| Performance | ~100MB RAM | ~20MB RAM |
| Startup Time | ~3s | ~0.5s |
| Type Safety | Runtime | Compile-time |
| Async | asyncio | tokio |
| Memory | HIM API | HIM API |
| Agents | Native Python | Subprocess to Python |
| LLM | OpenRouter | OpenRouter |
| Hormones | ✅ | ✅ |
| Presence | ✅ | ✅ |

## Contributing

This is a personal project. If you fork it:
1. Don't use it to violate Discord TOS at scale
2. Don't automate user accounts
3. Use for learning Rust and AI systems only

## License

This project inherits the license from the main SEL repository.

## Credits

- Original SEL Discord bot (Python version)
- [discord-selfbot](https://github.com/ege0x77czz/rust-discord-selfbot) Rust crate
- OpenRouter for LLM API access
- Anthropic Claude & OpenAI GPT models

## Sources

- [discord-selfbot crate](https://crates.io/crates/discord-selfbot)
- [GitHub: rust-discord-selfbot](https://github.com/ege0x77czz/rust-discord-selfbot)
