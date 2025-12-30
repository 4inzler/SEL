mod agents;
mod config;
mod hormones;
mod llm_client;
mod memory;
mod prompts;

use anyhow::Result;
use serenity::async_trait;
use serenity::client::{Client, Context, EventHandler};
use serenity::model::channel::Message;
use serenity::model::gateway::Ready;
use serenity::model::id::{ChannelId, UserId};
use serenity::model::voice::VoiceState;
use serenity::prelude::*;
use songbird::SerenityInit;
use std::collections::HashMap;
use std::sync::Arc;
use tracing::{error, info, warn};

use agents::AgentManager;
use config::Config;
use hormones::HormoneState;
use llm_client::LlmClient;
use memory::MemoryManager;

#[derive(Clone)]
struct ChannelState {
    hormones: HormoneState,
}

#[derive(Clone)]
struct HistoryMessage {
    author: String,
    content: String,
    is_bot: bool,
}

struct VoiceBot {
    config: Arc<Config>,
    llm_client: Arc<LlmClient>,
    memory_manager: Arc<MemoryManager>,
    agent_manager: Arc<AgentManager>,
    following_user_id: Arc<RwLock<Option<UserId>>>,
    channel_states: Arc<RwLock<HashMap<String, ChannelState>>>,
    message_history: Arc<RwLock<HashMap<String, Vec<HistoryMessage>>>>,
}

impl VoiceBot {
    fn new(config: Arc<Config>) -> Self {
        let llm_client = Arc::new(LlmClient::new(config.clone()));
        let memory_manager = Arc::new(MemoryManager::new(config.clone()));
        let agent_manager = Arc::new(AgentManager::new(config.clone()));

        Self {
            config,
            llm_client,
            memory_manager,
            agent_manager,
            following_user_id: Arc::new(RwLock::new(None)),
            channel_states: Arc::new(RwLock::new(HashMap::new())),
            message_history: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    fn get_or_create_channel_state(&self, channel_id: &str) -> ChannelState {
        let mut states = self.channel_states.blocking_write();
        states
            .entry(channel_id.to_string())
            .or_insert_with(|| ChannelState {
                hormones: HormoneState::default(),
            })
            .clone()
    }

    fn update_channel_state(&self, channel_id: &str, state: ChannelState) {
        let mut states = self.channel_states.blocking_write();
        states.insert(channel_id.to_string(), state);
    }

    fn add_to_history(&self, channel_id: &str, author: String, content: String, is_bot: bool) {
        let mut history = self.message_history.blocking_write();
        let messages = history
            .entry(channel_id.to_string())
            .or_insert_with(Vec::new);

        messages.push(HistoryMessage {
            author,
            content,
            is_bot,
        });

        if messages.len() > self.config.recent_context_limit {
            messages.drain(0..messages.len() - self.config.recent_context_limit);
        }
    }

    fn get_recent_messages(&self, channel_id: &str) -> Vec<(String, String, bool)> {
        let history = self.message_history.blocking_read();
        history
            .get(channel_id)
            .map(|msgs| {
                msgs.iter()
                    .map(|m| (m.author.clone(), m.content.clone(), m.is_bot))
                    .collect()
            })
            .unwrap_or_default()
    }

    async fn process_message(&self, ctx: Context, msg: Message) -> Result<()> {
        let channel_id = msg.channel_id.to_string();
        let user_id = msg.author.id.to_string();
        let user_name = msg.author.name.clone();
        let content = msg.content.clone();

        // Skip bot messages
        if msg.author.bot {
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

        let mut memories = Vec::new();
        let response = if let Some((agent_name, query)) = agent_result {
            // Execute agent
            info!("Invoking agent: {} with query: {}", agent_name, query);
            match self.agent_manager.run_agent(&agent_name, &query).await {
                Ok(result) => {
                    if result.starts_with("IMAGE:") {
                        let lines: Vec<&str> = result.split('\n').collect();
                        lines[1..].join("\n")
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

            let system_messages =
                prompts::build_system_prompt(&state.hormones, "", &memory_context);

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

        // Send response
        if let Err(e) = msg.reply(&ctx, &response).await {
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
        self.add_to_history(&channel_id, "VoiceBot".to_string(), response.clone(), true);

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

    async fn join_voice_channel(&self, ctx: &Context, msg: &Message, channel_id: ChannelId) -> Result<()> {
        let guild_id = msg.guild_id.ok_or_else(|| anyhow::anyhow!("Not in a guild"))?;

        let manager = songbird::get(ctx).await.expect("Songbird client not found");

        // Leave current channel if in one
        let _ = manager.remove(guild_id).await;

        // Join the new channel
        match manager.join(guild_id, channel_id).await {
            Ok(_) => {
                info!("Joined voice channel {}", channel_id);
                let _ = msg.reply(ctx, format!("✅ Joined voice channel {}", channel_id)).await;
                Ok(())
            }
            Err(e) => {
                error!("Failed to join channel: {}", e);
                Err(e.into())
            }
        }
    }
}

#[async_trait]
impl EventHandler for VoiceBot {
    async fn ready(&self, _ctx: Context, ready: Ready) {
        info!("🤖 {} is ready!", ready.user.name);
        info!("Bot ID: {}", ready.user.id);
        info!("Voice Commands:");
        info!("  !join <channel_id> - Join a voice channel by ID");
        info!("  !follow <user_id> - Follow a user through voice channels");
        info!("  !unfollow - Stop following");
        info!("  !leave - Leave current voice channel");
        info!("Also responds to normal messages with AI conversations!");
    }

    async fn message(&self, ctx: Context, msg: Message) {
        let content = msg.content.trim();

        // Voice commands
        if content.starts_with("!join ") {
            let channel_id_str = content.strip_prefix("!join ").unwrap().trim();
            match channel_id_str.parse::<u64>() {
                Ok(channel_id) => {
                    if let Err(e) = self.join_voice_channel(&ctx, &msg, ChannelId::new(channel_id)).await {
                        error!("Failed to join channel: {}", e);
                        let _ = msg.reply(&ctx, format!("❌ Failed to join: {}", e)).await;
                    }
                }
                Err(_) => {
                    let _ = msg.reply(&ctx, "❌ Invalid channel ID. Usage: `!join <channel_id>`").await;
                }
            }
            return;
        }

        if content.starts_with("!follow ") {
            let user_id_str = content.strip_prefix("!follow ").unwrap().trim();
            match user_id_str.parse::<u64>() {
                Ok(user_id) => {
                    let user_id = UserId::new(user_id);
                    *self.following_user_id.write().await = Some(user_id);

                    info!("Now following user {}", user_id);
                    let _ = msg.reply(&ctx, format!("✅ Now following user {}", user_id)).await;

                    // Try to join them immediately if they're in a VC
                    if let Some(guild_id) = msg.guild_id {
                        // Extract channel_id from cache before await to avoid holding CacheRef
                        let channel_id_opt = ctx.cache.guild(guild_id)
                            .and_then(|guild| guild.voice_states.get(&user_id)
                            .and_then(|vs| vs.channel_id));

                        if let Some(channel_id) = channel_id_opt {
                            info!("User is in channel {}, joining...", channel_id);
                            if let Err(e) = self.join_voice_channel(&ctx, &msg, channel_id).await {
                                error!("Failed to follow user: {}", e);
                            }
                        }
                    }
                }
                Err(_) => {
                    let _ = msg.reply(&ctx, "❌ Invalid user ID. Usage: `!follow <user_id>`").await;
                }
            }
            return;
        }

        if content == "!unfollow" {
            *self.following_user_id.write().await = None;
            info!("Stopped following");
            let _ = msg.reply(&ctx, "✅ Stopped following").await;
            return;
        }

        if content == "!leave" {
            if let Some(guild_id) = msg.guild_id {
                let manager = songbird::get(&ctx).await.expect("Songbird client not found");

                if manager.get(guild_id).is_some() {
                    if let Err(e) = manager.remove(guild_id).await {
                        error!("Failed to leave voice: {}", e);
                        let _ = msg.reply(&ctx, format!("❌ Failed to leave: {}", e)).await;
                    } else {
                        info!("Left voice channel in guild {}", guild_id);
                        let _ = msg.reply(&ctx, "✅ Left voice channel").await;
                    }
                } else {
                    let _ = msg.reply(&ctx, "❌ Not in a voice channel").await;
                }
            }
            return;
        }

        // Process normal messages with AI
        if let Err(e) = self.process_message(ctx, msg).await {
            error!("Error processing message: {}", e);
        }
    }

    async fn voice_state_update(&self, ctx: Context, old: Option<VoiceState>, new: VoiceState) {
        // Check if we're following this user
        let following_id = *self.following_user_id.read().await;
        if following_id != Some(new.user_id) {
            return;
        }

        info!("Followed user voice state changed");

        // Get the guild ID
        let guild_id = match new.guild_id {
            Some(id) => id,
            None => return,
        };

        let manager = songbird::get(&ctx).await.expect("Songbird client not found");

        // User joined/moved to a channel
        if let Some(channel_id) = new.channel_id {
            info!("Following user to channel {}", channel_id);

            // Leave current channel if in one
            let _ = manager.remove(guild_id).await;

            // Join the new channel
            match manager.join(guild_id, channel_id).await {
                Ok(_) => info!("Successfully followed to channel {}", channel_id),
                Err(e) => error!("Failed to follow to channel: {}", e),
            }
        }
        // User left voice
        else if old.is_some() && old.as_ref().unwrap().channel_id.is_some() {
            info!("Followed user left voice, disconnecting");
            let _ = manager.remove(guild_id).await;
        }
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

    info!("🚀 Starting Voice Bot with AI...");

    // Load configuration
    let config = Arc::new(Config::from_env()?);

    info!("Loaded configuration:");
    info!("  Main model: {}", config.openrouter_main_model);
    info!("  Agents dir: {}", config.agents_dir);

    // Create bot handler
    let handler = VoiceBot::new(config.clone());

    // Build client with voice support
    let intents = GatewayIntents::GUILDS
        | GatewayIntents::GUILD_MESSAGES
        | GatewayIntents::MESSAGE_CONTENT
        | GatewayIntents::GUILD_VOICE_STATES;

    let mut client = Client::builder(&config.discord_bot_token, intents)
        .event_handler(handler)
        .register_songbird()
        .await?;

    info!("✅ Connected! Voice bot is now listening...");

    // Start client
    if let Err(e) = client.start().await {
        error!("Client error: {}", e);
    }

    Ok(())
}
