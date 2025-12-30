use anyhow::{Context, Result};
use serenity_self::model::id::{ChannelId, GuildId, UserId};
use serenity_self::prelude::*;
use songbird::input::{Input, Reader};
use songbird::{Event, EventContext, EventHandler as VoiceEventHandler, TrackEvent};
use songbird::model::payload::{ClientDisconnect, Speaking};
use std::io::Cursor;
use std::sync::Arc;
use tokio::sync::{mpsc, RwLock};
use tracing::{error, info, warn};

use crate::config::Config;
use crate::elevenlabs::ElevenLabsClient;
use crate::stt::SttClient;

pub struct VoiceManager {
    config: Arc<Config>,
    elevenlabs: Arc<ElevenLabsClient>,
    stt_client: Arc<SttClient>,
    current_guild: Arc<RwLock<Option<GuildId>>>,
    current_channel: Arc<RwLock<Option<ChannelId>>>,
    transcription_tx: Arc<RwLock<Option<mpsc::UnboundedSender<(UserId, String)>>>>,
}

impl VoiceManager {
    pub fn new(config: Arc<Config>, transcription_tx: mpsc::UnboundedSender<(UserId, String)>) -> Self {
        let elevenlabs = Arc::new(ElevenLabsClient::new(config.clone()));
        let stt_client = Arc::new(SttClient::new(config.clone()));
        Self {
            config,
            elevenlabs,
            stt_client,
            current_guild: Arc::new(RwLock::new(None)),
            current_channel: Arc::new(RwLock::new(None)),
            transcription_tx: Arc::new(RwLock::new(Some(transcription_tx))),
        }
    }

    pub async fn join_voice_channel(
        &self,
        ctx: &Context,
        guild_id: GuildId,
        channel_id: ChannelId,
    ) -> Result<()> {
        let manager = songbird::get(ctx)
            .await
            .context("Songbird not initialized")?;

        let (handler_lock, result) = manager.join(guild_id, channel_id).await;

        match result {
            Ok(()) => {
                info!(
                    "Joined voice channel {} in guild {}",
                    channel_id, guild_id
                );

                // Store current location
                *self.current_guild.write().await = Some(guild_id);
                *self.current_channel.write().await = Some(channel_id);

                // Add event handlers
                let mut handler = handler_lock.lock().await;
                handler.add_global_event(
                    Event::Track(TrackEvent::End),
                    TrackEndNotifier,
                );

                // Add voice receiver if STT is enabled
                if self.config.stt_enabled && !self.config.elevenlabs_api_key.is_empty() {
                    let receiver = VoiceReceiver::new(
                        self.stt_client.clone(),
                        self.transcription_tx.read().await.clone(),
                    );
                    handler.add_global_event(
                        Event::Core(songbird::CoreEvent::SpeakingStateUpdate),
                        receiver.clone(),
                    );
                    handler.add_global_event(
                        Event::Core(songbird::CoreEvent::VoicePacket),
                        receiver,
                    );
                    info!("Voice receiving enabled with STT");
                }

                Ok(())
            }
            Err(e) => {
                error!("Failed to join voice channel: {}", e);
                Err(anyhow::anyhow!("Failed to join: {}", e))
            }
        }
    }

    pub async fn leave_voice_channel(&self, ctx: &Context) -> Result<()> {
        let guild_id = self
            .current_guild
            .read()
            .await
            .context("Not in any voice channel")?;

        let manager = songbird::get(ctx)
            .await
            .context("Songbird not initialized")?;

        manager.remove(guild_id).await?;

        info!("Left voice channel in guild {}", guild_id);

        // Clear current location
        *self.current_guild.write().await = None;
        *self.current_channel.write().await = None;

        Ok(())
    }

    pub async fn speak(&self, ctx: &Context, text: &str) -> Result<()> {
        let guild_id = self
            .current_guild
            .read()
            .await
            .context("Not in any voice channel")?;

        info!("Generating speech for: {}", text);

        // Generate speech using ElevenLabs
        let audio_bytes = self
            .elevenlabs
            .text_to_speech(text)
            .await
            .context("Failed to generate speech")?;

        info!("Generated {} bytes of audio", audio_bytes.len());

        // Get voice manager
        let manager = songbird::get(ctx)
            .await
            .context("Songbird not initialized")?;

        if let Some(handler_lock) = manager.get(guild_id) {
            let mut handler = handler_lock.lock().await;

            // Create audio source from bytes
            let cursor = Cursor::new(audio_bytes.to_vec());
            let source = Reader::Extension(Box::new(cursor));
            let input = Input::from(source);

            // Play audio
            let track_handle = handler.play_input(input);

            info!("Playing audio in voice channel");

            Ok(())
        } else {
            Err(anyhow::anyhow!("Not connected to voice in guild"))
        }
    }

    pub async fn is_in_voice(&self) -> bool {
        self.current_guild.read().await.is_some()
    }

    pub async fn get_current_channel(&self) -> Option<ChannelId> {
        *self.current_channel.read().await
    }
}

struct TrackEndNotifier;

#[async_trait::async_trait]
impl VoiceEventHandler for TrackEndNotifier {
    async fn act(&self, ctx: &EventContext<'_>) -> Option<Event> {
        if let EventContext::Track(_track_list) = ctx {
            info!("Track finished playing");
        }
        None
    }
}

// Voice receiver for STT
#[derive(Clone)]
struct VoiceReceiver {
    stt_client: Arc<SttClient>,
    transcription_tx: Option<mpsc::UnboundedSender<(UserId, String)>>,
    audio_buffers: Arc<RwLock<std::collections::HashMap<u32, Vec<u8>>>>,
}

impl VoiceReceiver {
    fn new(
        stt_client: Arc<SttClient>,
        transcription_tx: Option<mpsc::UnboundedSender<(UserId, String)>>,
    ) -> Self {
        Self {
            stt_client,
            transcription_tx,
            audio_buffers: Arc::new(RwLock::new(std::collections::HashMap::new())),
        }
    }
}

#[async_trait::async_trait]
impl VoiceEventHandler for VoiceReceiver {
    async fn act(&self, ctx: &EventContext<'_>) -> Option<Event> {
        match ctx {
            EventContext::SpeakingStateUpdate(Speaking {
                speaking,
                ssrc,
                user_id,
                ..
            }) => {
                // User started or stopped speaking
                if !speaking {
                    // User stopped speaking - process their audio
                    let mut buffers = self.audio_buffers.write().await;
                    if let Some(audio_data) = buffers.remove(ssrc) {
                        if audio_data.len() > 1024 {
                            // Only transcribe if we have enough audio
                            let stt_client = self.stt_client.clone();
                            let tx = self.transcription_tx.clone();
                            let user_id = user_id.map(|id| UserId::from(id.0));

                            tokio::spawn(async move {
                                match stt_client.transcribe_audio(audio_data).await {
                                    Ok(text) if !text.trim().is_empty() => {
                                        info!("Transcribed: {}", text);
                                        if let (Some(tx), Some(uid)) = (tx, user_id) {
                                            let _ = tx.send((uid, text));
                                        }
                                    }
                                    Ok(_) => {} // Empty transcription
                                    Err(e) => {
                                        warn!("STT transcription failed: {}", e);
                                    }
                                }
                            });
                        }
                    }
                }
            }
            EventContext::VoicePacket(packet) => {
                // Received voice packet - add to buffer
                if let Some(audio) = packet.audio {
                    let mut buffers = self.audio_buffers.write().await;
                    buffers
                        .entry(packet.packet.ssrc)
                        .or_insert_with(Vec::new)
                        .extend_from_slice(&audio);
                }
            }
            _ => {}
        }
        None
    }
}

// Helper function to find user's voice channel
pub async fn find_user_voice_channel(
    ctx: &Context,
    guild_id: GuildId,
    user_id: serenity_self::model::id::UserId,
) -> Option<ChannelId> {
    let guild = guild_id.to_guild_cached(&ctx.cache)?;

    for (channel_id, channel) in guild.voice_states.iter() {
        if channel.user_id == user_id {
            return channel.channel_id;
        }
    }

    None
}
