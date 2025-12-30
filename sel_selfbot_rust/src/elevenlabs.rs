use anyhow::{Context, Result};
use bytes::Bytes;
use serde::{Deserialize, Serialize};
use std::sync::Arc;

use crate::config::Config;

#[derive(Debug, Serialize)]
struct TtsRequest {
    text: String,
    model_id: String,
    voice_settings: VoiceSettings,
}

#[derive(Debug, Serialize)]
struct VoiceSettings {
    stability: f32,
    similarity_boost: f32,
    style: f32,
    use_speaker_boost: bool,
}

pub struct ElevenLabsClient {
    config: Arc<Config>,
    client: reqwest::Client,
}

impl ElevenLabsClient {
    pub fn new(config: Arc<Config>) -> Self {
        Self {
            config,
            client: reqwest::Client::new(),
        }
    }

    pub async fn text_to_speech(&self, text: &str) -> Result<Bytes> {
        let voice_id = &self.config.elevenlabs_voice_id;
        let url = format!(
            "https://api.elevenlabs.io/v1/text-to-speech/{}",
            voice_id
        );

        let request = TtsRequest {
            text: text.to_string(),
            model_id: self.config.elevenlabs_model.clone(),
            voice_settings: VoiceSettings {
                stability: self.config.elevenlabs_stability,
                similarity_boost: self.config.elevenlabs_similarity,
                style: self.config.elevenlabs_style,
                use_speaker_boost: true,
            },
        };

        let response = self
            .client
            .post(&url)
            .header("xi-api-key", &self.config.elevenlabs_api_key)
            .header("Content-Type", "application/json")
            .json(&request)
            .send()
            .await
            .context("Failed to send TTS request to ElevenLabs")?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            anyhow::bail!("ElevenLabs API error {}: {}", status, error_text);
        }

        let audio_bytes = response
            .bytes()
            .await
            .context("Failed to read audio bytes from ElevenLabs")?;

        Ok(audio_bytes)
    }

    pub async fn get_available_voices(&self) -> Result<Vec<Voice>> {
        let url = "https://api.elevenlabs.io/v1/voices";

        let response = self
            .client
            .get(url)
            .header("xi-api-key", &self.config.elevenlabs_api_key)
            .send()
            .await
            .context("Failed to fetch voices from ElevenLabs")?;

        if !response.status().is_success() {
            anyhow::bail!("Failed to get voices: {}", response.status());
        }

        let voices_response: VoicesResponse = response.json().await?;
        Ok(voices_response.voices)
    }
}

#[derive(Debug, Deserialize)]
struct VoicesResponse {
    voices: Vec<Voice>,
}

#[derive(Debug, Deserialize)]
pub struct Voice {
    pub voice_id: String,
    pub name: String,
    pub description: Option<String>,
}
