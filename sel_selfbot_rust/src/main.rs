mod agents;
mod config;
// mod elevenlabs;  // Temporarily disabled
mod hormones;
mod llm_client;
mod memory;
mod presence;
mod prompts;
// mod stt;  // Temporarily disabled
// mod voice;  // Temporarily disabled

use anyhow::Result;
use async_trait::async_trait;
use serenity_self::all::GatewayIntents;
use serenity_self::client::{Context, EventHandler};
use serenity_self::model::channel::Message;
use serenity_self::model::gateway::Ready;
use serenity_self::prelude::*;
use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use tracing::{error, info, warn};

use agents::AgentManager;
use config::Config;
use hormones::HormoneState;
use llm_client::LlmClient;
use memory::MemoryManager;
use presence::PresenceTracker;

struct SelHandler {
    config: Arc<Config>,
    llm_client: Arc<LlmClient>,
    memory_manager: Arc<MemoryManager>,
    agent_manager: Arc<AgentManager>,
    presence_tracker: Arc<PresenceTracker>,
    channel_states: Arc<RwLock<HashMap<String, ChannelState>>>,
    message_history: Arc<RwLock<HashMap<String, Vec<HistoryMessage>>>>,
}

#[derive(Clone)]
struct ChannelState {
    hormones: HormoneState,
}

#[derive(Clone)]
struct HistoryMessage {
    author: String,
    content: String,
    is_sel: bool,
}

impl SelHandler {
    fn new(config: Arc<Config>) -> Self {
        let llm_client = Arc::new(LlmClient::new(config.clone()));
        let memory_manager = Arc::new(MemoryManager::new(config.clone()));
        let agent_manager = Arc::new(AgentManager::new(config.clone()));
        let presence_tracker = Arc::new(PresenceTracker::new());

        Self {
            config,
            llm_client,
            memory_manager,
            agent_manager,
            presence_tracker,
            channel_states: Arc::new(RwLock::new(HashMap::new())),
            message_history: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    fn get_or_create_channel_state(&self, channel_id: &str) -> ChannelState {
        let mut states = self.channel_states.write().unwrap();
        states
            .entry(channel_id.to_string())
            .or_insert_with(|| ChannelState {
                hormones: HormoneState::default(),
            })
            .clone()
    }

    fn update_channel_state(&self, channel_id: &str, state: ChannelState) {
        let mut states = self.channel_states.write().unwrap();
        states.insert(channel_id.to_string(), state);
    }

    fn add_to_history(&self, channel_id: &str, author: String, content: String, is_sel: bool) {
        let mut history = self.message_history.write().unwrap();
        let messages = history
            .entry(channel_id.to_string())
            .or_insert_with(Vec::new);

        messages.push(HistoryMessage {
            author,
            content,
            is_sel,
        });

        if messages.len() > self.config.recent_context_limit {
            messages.drain(0..messages.len() - self.config.recent_context_limit);
        }
    }

    fn get_recent_messages(&self, channel_id: &str) -> Vec<(String, String, bool)> {
        let history = self.message_history.read().unwrap();
        history
            .get(channel_id)
            .map(|msgs| {
                msgs.iter()
                    .map(|m| (m.author.clone(), m.content.clone(), m.is_sel))
                    .collect()
            })
            .unwrap_or_default()
    }

    async fn process_message(&self, ctx: Context, msg: Message) -> Result<()> {
        let channel_id = msg.channel_id.to_string();
        let user_id = msg.author.id.to_string();
        let user_name = msg.author.name.clone();
        let content = msg.content.clone();

        // Skip messages from self
        if msg.author.bot {
            return Ok(());
        }

        // Check whitelist
        if !self.config.whitelist_channel_ids.is_empty()
            && !self
                .config
                .whitelist_channel_ids
                .contains(&channel_id)
        {
            return Ok(());
        }

        info!("Processing message from {} in {}", user_name, channel_id);

        // Add to history
        self.add_to_history(&channel_id, user_name.clone(), content.clone(), false);

        // Get channel state
        let mut state = self.get_or_create_channel_state(&channel_id);
        state.hormones.decay();

        // Check for agent invocation
        let agent_result = if let Some((agent_name, query)) =
            self.agent_manager.detect_agent_invocation(&content)
        {
            Some((agent_name, query))
        } else {
            self.agent_manager
                .classify_and_maybe_invoke(&content, &user_id, &self.llm_client)
                .await
        };

        let mut memories = Vec::new();  // Initialize memories outside the block
        let response = if let Some((agent_name, query)) = agent_result {
            // Execute agent
            info!("Invoking agent: {} with query: {}", agent_name, query);
            match self.agent_manager.run_agent(&agent_name, &query).await {
                Ok(result) => {
                    if result.starts_with("IMAGE:") {
                        let lines: Vec<&str> = result.split('\n').collect();
                        let message_text = lines[1..].join("\n");
                        message_text
                    } else {
                        result
                    }
                }
                Err(e) => {
                    error!("Agent execution failed: {}", e);
                    format!("❌ Agent failed: {}", e)
                }
            }
        } else {
            // Normal conversation - query memory and generate response
            memories = self
                .memory_manager
                .retrieve(&user_id, &content)
                .await
                .unwrap_or_default();

            let memory_context = self.memory_manager.format_memories_for_prompt(&memories);
            let presence_context = self.presence_tracker.get_context_for_prompt(5);

            let system_messages =
                prompts::build_system_prompt(&state.hormones, &presence_context, &memory_context);

            let recent = self.get_recent_messages(&channel_id);
            let mut messages = prompts::build_conversation_messages(system_messages, recent);

            messages.push(llm_client::Message {
                role: "user".to_string(),
                content: format!("{}: {}", user_name, content),
            });

            match self.llm_client.generate_main(messages, Some(1000)).await {
                Ok(response) => response,
                Err(e) => {
                    error!("LLM generation failed: {}", e);
                    "I'm having trouble thinking right now...".to_string()
                }
            }
        };

        // Send text response
        use serenity_self::json::json;
        let map = json!({
            "content": response,
        });

        if let Err(e) = ctx.http.send_message(msg.channel_id.into(), Vec::new(), &map).await {
            let error_msg = format!("{}", e);
            if error_msg.contains("401") || error_msg.contains("Unauthorized") {
                error!("🚨 AUTHENTICATION FAILED - Token may be invalid or expired");
            } else if error_msg.contains("403") || error_msg.contains("Forbidden") {
                error!("🚨 CAPTCHA LIKELY REQUIRED - Discord is challenging the account");
                error!("   Please solve the captcha in your Discord client or web browser");
            } else if error_msg.contains("429") || error_msg.contains("Too Many Requests") {
                warn!("⚠️  Rate limited - slow down message sending");
            } else {
                error!("Failed to send message: {}", e);
            }
        }

        // Add response to history
        self.add_to_history(&channel_id, "SEL".to_string(), response.clone(), true);

        // Update hormones
        let sentiment = if content.contains('?') {
            "question"
        } else if content.contains('!') {
            "positive"
        } else {
            "neutral"
        };

        state
            .hormones
            .update_from_interaction(sentiment, memories.is_empty());
        self.update_channel_state(&channel_id, state);

        // Store memory
        if let Err(e) = self
            .memory_manager
            .create_memory_from_interaction(&user_id, &content, &response, &user_name)
            .await
        {
            warn!("Failed to store memory: {}", e);
        }

        Ok(())
    }
}

#[async_trait]
impl EventHandler for SelHandler {
    async fn ready(&self, _ctx: Context, ready: Ready) {
        info!("🤖 {} is ready and connected!", ready.user.name);
        info!("User ID: {}", ready.user.id);
        info!("Monitoring channels for messages...");

        if !self.config.elevenlabs_api_key.is_empty() {
            info!("✅ Voice support enabled (ElevenLabs TTS)");
        } else {
            info!("⚠️  Voice TTS disabled (no ELEVENLABS_API_KEY)");
        }
    }

    async fn message(&self, ctx: Context, msg: Message) {
        if let Err(e) = self.process_message(ctx, msg).await {
            error!("Error processing message: {}", e);
        }
    }

    async fn resume(&self, _ctx: Context, _resume: serenity_self::model::event::ResumedEvent) {
        warn!("⚠️  Connection resumed - this may indicate rate limiting or captcha challenges");
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive(tracing::Level::INFO.into()),
        )
        .init();

    info!("🚀 Starting SEL Selfbot...");

    // Load configuration
    let config = Arc::new(Config::from_env()?);

    info!("Loaded configuration:");
    info!("  Main model: {}", config.openrouter_main_model);
    info!("  Memory dir: {}", config.him_memory_dir);
    info!("  Agents dir: {}", config.agents_dir);

    // Create handler
    let handler = SelHandler::new(config.clone());

    // Build client
    info!("Connecting to Discord...");
    let mut client = Client::builder(&config.discord_user_token, GatewayIntents::all())
        .event_handler(handler)
        .await?;

    info!("✅ Connected! SEL is now listening...");

    // Start client
    if let Err(e) = client.start().await {
        error!("Client error: {}", e);
    }

    Ok(())
}
