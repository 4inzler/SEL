use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::sync::Arc;

use crate::config::Config;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct OpenRouterRequest {
    model: String,
    messages: Vec<Message>,
    temperature: f32,
    top_p: f32,
    max_tokens: Option<u32>,
}

#[derive(Debug, Deserialize)]
struct OpenRouterResponse {
    choices: Vec<Choice>,
}

#[derive(Debug, Deserialize)]
struct Choice {
    message: Message,
}

pub struct LlmClient {
    config: Arc<Config>,
    client: reqwest::Client,
}

impl LlmClient {
    pub fn new(config: Arc<Config>) -> Self {
        Self {
            config,
            client: reqwest::Client::new(),
        }
    }

    pub async fn generate_main(
        &self,
        messages: Vec<Message>,
        max_tokens: Option<u32>,
    ) -> Result<String> {
        self.call_openrouter(
            &self.config.openrouter_main_model,
            messages,
            self.config.openrouter_main_temp,
            self.config.openrouter_top_p,
            max_tokens,
        )
        .await
    }

    pub async fn generate_utility(
        &self,
        messages: Vec<Message>,
        max_tokens: Option<u32>,
    ) -> Result<String> {
        self.call_openrouter(
            &self.config.openrouter_util_model,
            messages,
            self.config.openrouter_util_temp,
            self.config.openrouter_top_p,
            max_tokens,
        )
        .await
    }

    pub async fn generate_vision(
        &self,
        messages: Vec<Message>,
        max_tokens: Option<u32>,
    ) -> Result<String> {
        self.call_openrouter(
            &self.config.openrouter_vision_model,
            messages,
            self.config.openrouter_util_temp,
            self.config.openrouter_top_p,
            max_tokens,
        )
        .await
    }

    async fn call_openrouter(
        &self,
        model: &str,
        messages: Vec<Message>,
        temperature: f32,
        top_p: f32,
        max_tokens: Option<u32>,
    ) -> Result<String> {
        let request = OpenRouterRequest {
            model: model.to_string(),
            messages,
            temperature,
            top_p,
            max_tokens,
        };

        let response = self
            .client
            .post("https://openrouter.ai/api/v1/chat/completions")
            .header("Authorization", format!("Bearer {}", self.config.openrouter_api_key))
            .header("HTTP-Referer", "https://github.com/your-repo/sel-selfbot")
            .header("X-Title", "SEL Selfbot")
            .json(&request)
            .send()
            .await
            .context("Failed to send OpenRouter request")?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            anyhow::bail!("OpenRouter API error {}: {}", status, error_text);
        }

        let or_response: OpenRouterResponse = response
            .json()
            .await
            .context("Failed to parse OpenRouter response")?;

        or_response
            .choices
            .first()
            .map(|c| c.message.content.clone())
            .context("No response from OpenRouter")
    }

    pub async fn classify_intent(&self, user_message: &str, user_id: &str, approved_user_id: &str) -> Result<String> {
        // Only classify for approved users
        if user_id != approved_user_id {
            return Ok("normal".to_string());
        }

        let messages = vec![
            Message {
                role: "system".to_string(),
                content: r#"You are a message classifier. Determine if the user wants to:
- "system": Run a system command, check processes, disk space, etc.
- "normal": Regular conversation

Respond with ONLY one word: "system" or "normal""#.to_string(),
            },
            Message {
                role: "user".to_string(),
                content: user_message.to_string(),
            },
        ];

        let result = self.generate_utility(messages, Some(10)).await?;
        Ok(result.trim().to_lowercase())
    }
}
