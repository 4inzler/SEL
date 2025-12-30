use anyhow::{Context, Result};
use bytes::Bytes;
use reqwest::multipart;
use serde::{Deserialize, Serialize};
use std::sync::Arc;

use crate::config::Config;

#[derive(Debug, Deserialize)]
struct SttResponse {
    text: String,
}

pub struct SttClient {
    config: Arc<Config>,
    client: reqwest::Client,
}

impl SttClient {
    pub fn new(config: Arc<Config>) -> Self {
        Self {
            config,
            client: reqwest::Client::new(),
        }
    }

    pub async fn transcribe_audio(&self, audio_data: Vec<u8>) -> Result<String> {
        // ElevenLabs STT API endpoint
        let url = "https://api.elevenlabs.io/v1/speech-to-text";

        // Create multipart form with audio file
        let audio_part = multipart::Part::bytes(audio_data)
            .file_name("audio.webm")
            .mime_str("audio/webm")?;

        let form = multipart::Form::new()
            .part("audio", audio_part)
            .text("model_id", self.config.elevenlabs_stt_model.clone());

        let response = self
            .client
            .post(url)
            .header("xi-api-key", &self.config.elevenlabs_api_key)
            .multipart(form)
            .send()
            .await
            .context("Failed to send ElevenLabs STT request")?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            anyhow::bail!("ElevenLabs STT API error {}: {}", status, error_text);
        }

        let stt_response: SttResponse = response
            .json()
            .await
            .context("Failed to parse ElevenLabs STT response")?;

        Ok(stt_response.text)
    }
}
