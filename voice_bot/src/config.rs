use std::env;

#[derive(Debug, Clone)]
pub struct Config {
    // Discord
    pub discord_bot_token: String,
    pub approval_user_id: String,
    pub whitelist_channel_ids: Vec<String>,

    // LLM Configuration
    pub openrouter_api_key: String,
    pub openrouter_main_model: String,
    pub openrouter_util_model: String,
    pub openrouter_vision_model: String,
    pub openrouter_main_temp: f32,
    pub openrouter_util_temp: f32,
    pub openrouter_top_p: f32,

    // Memory Configuration
    pub him_memory_dir: String,
    pub him_memory_levels: u8,
    pub him_api_base_url: String,
    pub memory_recall_limit: usize,
    pub recent_context_limit: usize,

    // Agent Configuration
    pub agents_dir: String,

    // Terminal Control (for system_agent)
    pub tmux_control_url: String,
    pub tmux_control_token: String,

    // Bot Behavior
    pub sel_timezone: String,
    pub inactivity_ping_hours: f32,
    pub inactivity_ping_cooldown_hours: f32,

    // SwarmUI
    pub swarmui_url: String,
    pub swarmui_api_key: String,

    // ElevenLabs TTS
    pub elevenlabs_api_key: String,
    pub elevenlabs_voice_id: String,
    pub elevenlabs_model: String,
    pub elevenlabs_stability: f32,
    pub elevenlabs_similarity: f32,
    pub elevenlabs_style: f32,

    // ElevenLabs STT (Speech-to-Text)
    pub elevenlabs_stt_model: String,
    pub stt_enabled: bool,
}

impl Config {
    pub fn from_env() -> anyhow::Result<Self> {
        // Try to load from selfbot.env first, then fall back to .env
        dotenv::from_filename("selfbot.env").or_else(|_| dotenv::dotenv()).ok();

        Ok(Config {
            // Discord
            discord_bot_token: env::var("DISCORD_BOT_TOKEN")
                .expect("DISCORD_BOT_TOKEN must be set"),
            approval_user_id: env::var("APPROVAL_USER_ID")
                .unwrap_or_else(|_| "1329883906069102733".to_string()),
            whitelist_channel_ids: env::var("WHITELIST_CHANNEL_IDS")
                .unwrap_or_default()
                .split(',')
                .filter(|s| !s.is_empty())
                .map(|s| s.to_string())
                .collect(),

            // LLM Configuration
            openrouter_api_key: env::var("OPENROUTER_API_KEY")
                .expect("OPENROUTER_API_KEY must be set"),
            openrouter_main_model: env::var("OPENROUTER_MAIN_MODEL")
                .unwrap_or_else(|_| "anthropic/claude-3.5-sonnet".to_string()),
            openrouter_util_model: env::var("OPENROUTER_UTIL_MODEL")
                .unwrap_or_else(|_| "anthropic/claude-3-haiku-20240307".to_string()),
            openrouter_vision_model: env::var("OPENROUTER_VISION_MODEL")
                .unwrap_or_else(|_| "openai/gpt-4o-mini".to_string()),
            openrouter_main_temp: env::var("OPENROUTER_MAIN_TEMP")
                .unwrap_or_else(|_| "0.8".to_string())
                .parse()
                .unwrap_or(0.8),
            openrouter_util_temp: env::var("OPENROUTER_UTIL_TEMP")
                .unwrap_or_else(|_| "0.3".to_string())
                .parse()
                .unwrap_or(0.3),
            openrouter_top_p: env::var("OPENROUTER_TOP_P")
                .unwrap_or_else(|_| "0.9".to_string())
                .parse()
                .unwrap_or(0.9),

            // Memory Configuration
            him_memory_dir: env::var("HIM_MEMORY_DIR")
                .unwrap_or_else(|_| "./sel_data/him_store".to_string()),
            him_memory_levels: env::var("HIM_MEMORY_LEVELS")
                .unwrap_or_else(|_| "3".to_string())
                .parse()
                .unwrap_or(3),
            him_api_base_url: env::var("HIM_API_BASE_URL")
                .unwrap_or_else(|_| "http://localhost:8000".to_string()),
            memory_recall_limit: env::var("MEMORY_RECALL_LIMIT")
                .unwrap_or_else(|_| "10".to_string())
                .parse()
                .unwrap_or(10),
            recent_context_limit: env::var("RECENT_CONTEXT_LIMIT")
                .unwrap_or_else(|_| "20".to_string())
                .parse()
                .unwrap_or(20),

            // Agent Configuration
            agents_dir: env::var("AGENTS_DIR")
                .unwrap_or_else(|_| "./agents".to_string()),

            // Terminal Control
            tmux_control_url: env::var("TMUX_CONTROL_URL")
                .unwrap_or_else(|_| "http://localhost:9001".to_string()),
            tmux_control_token: env::var("TMUX_CONTROL_TOKEN")
                .unwrap_or_default(),

            // Bot Behavior
            sel_timezone: env::var("SEL_TIMEZONE")
                .unwrap_or_else(|_| "America/Los_Angeles".to_string()),
            inactivity_ping_hours: env::var("INACTIVITY_PING_HOURS")
                .unwrap_or_else(|_| "48.0".to_string())
                .parse()
                .unwrap_or(48.0),
            inactivity_ping_cooldown_hours: env::var("INACTIVITY_PING_COOLDOWN_HOURS")
                .unwrap_or_else(|_| "24.0".to_string())
                .parse()
                .unwrap_or(24.0),

            // SwarmUI
            swarmui_url: env::var("SWARMUI_URL")
                .unwrap_or_else(|_| "http://localhost:7801".to_string()),
            swarmui_api_key: env::var("SWARMUI_API_KEY")
                .unwrap_or_default(),

            // ElevenLabs TTS
            elevenlabs_api_key: env::var("ELEVENLABS_API_KEY")
                .unwrap_or_default(),
            elevenlabs_voice_id: env::var("ELEVENLABS_VOICE_ID")
                .unwrap_or_else(|_| "21m00Tcm4TlvDq8ikWAM".to_string()), // Rachel voice
            elevenlabs_model: env::var("ELEVENLABS_MODEL")
                .unwrap_or_else(|_| "eleven_monolingual_v1".to_string()),
            elevenlabs_stability: env::var("ELEVENLABS_STABILITY")
                .unwrap_or_else(|_| "0.5".to_string())
                .parse()
                .unwrap_or(0.5),
            elevenlabs_similarity: env::var("ELEVENLABS_SIMILARITY")
                .unwrap_or_else(|_| "0.75".to_string())
                .parse()
                .unwrap_or(0.75),
            elevenlabs_style: env::var("ELEVENLABS_STYLE")
                .unwrap_or_else(|_| "0.0".to_string())
                .parse()
                .unwrap_or(0.0),

            // ElevenLabs STT
            elevenlabs_stt_model: env::var("ELEVENLABS_STT_MODEL")
                .unwrap_or_else(|_| "eleven_multilingual_v2".to_string()),
            stt_enabled: env::var("STT_ENABLED")
                .unwrap_or_else(|_| "true".to_string())
                .parse()
                .unwrap_or(true),
        })
    }
}
