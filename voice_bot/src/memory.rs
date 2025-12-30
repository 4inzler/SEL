use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

use crate::config::Config;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Memory {
    pub summary: String,
    pub content: String,
    pub timestamp: DateTime<Utc>,
    pub salience: f32,
    pub stream_id: String,
}

#[derive(Debug, Serialize)]
struct QueryRequest {
    stream_id: String,
    query: String,
    limit: usize,
}

#[derive(Debug, Deserialize)]
struct QueryResponse {
    memories: Vec<Memory>,
}

#[derive(Debug, Serialize)]
struct StoreRequest {
    stream_id: String,
    content: String,
    summary: String,
    salience: f32,
}

pub struct MemoryManager {
    config: Arc<Config>,
    client: reqwest::Client,
}

impl MemoryManager {
    pub fn new(config: Arc<Config>) -> Self {
        Self {
            config,
            client: reqwest::Client::new(),
        }
    }

    pub async fn retrieve(&self, stream_id: &str, query: &str) -> Result<Vec<Memory>> {
        let request = QueryRequest {
            stream_id: stream_id.to_string(),
            query: query.to_string(),
            limit: self.config.memory_recall_limit,
        };

        let response = self
            .client
            .post(format!("{}/v1/query", self.config.him_api_base_url))
            .json(&request)
            .send()
            .await
            .context("Failed to query HIM API")?;

        if !response.status().is_success() {
            // HIM API might not be running, return empty memories
            tracing::warn!("HIM API unavailable: {}", response.status());
            return Ok(Vec::new());
        }

        let query_response: QueryResponse = response
            .json()
            .await
            .context("Failed to parse HIM response")?;

        Ok(query_response.memories)
    }

    pub async fn store(
        &self,
        stream_id: &str,
        content: &str,
        summary: &str,
        salience: f32,
    ) -> Result<()> {
        let request = StoreRequest {
            stream_id: stream_id.to_string(),
            content: content.to_string(),
            summary: summary.to_string(),
            salience,
        };

        let response = self
            .client
            .post(format!("{}/v1/tiles", self.config.him_api_base_url))
            .json(&request)
            .send()
            .await;

        match response {
            Ok(resp) if resp.status().is_success() => Ok(()),
            Ok(resp) => {
                tracing::warn!("Failed to store memory: {}", resp.status());
                Ok(()) // Don't fail if memory storage fails
            }
            Err(e) => {
                tracing::warn!("HIM API unavailable: {}", e);
                Ok(()) // Don't fail if HIM is down
            }
        }
    }

    pub fn format_memories_for_prompt(&self, memories: &[Memory]) -> String {
        if memories.is_empty() {
            return String::new();
        }

        let mut result = String::from("[RELEVANT MEMORIES]\n");
        for (i, mem) in memories.iter().enumerate() {
            let age = Utc::now() - mem.timestamp;
            let age_str = if age.num_days() > 0 {
                format!("{}d ago", age.num_days())
            } else if age.num_hours() > 0 {
                format!("{}h ago", age.num_hours())
            } else {
                format!("{}m ago", age.num_minutes())
            };

            result.push_str(&format!(
                "{}. [{}] {}\n",
                i + 1,
                age_str,
                mem.summary
            ));
        }
        result.push_str("[/RELEVANT MEMORIES]\n");
        result
    }

    pub async fn create_memory_from_interaction(
        &self,
        stream_id: &str,
        user_message: &str,
        sel_response: &str,
        user_name: &str,
    ) -> Result<()> {
        let content = format!(
            "{}: {}\nSEL: {}",
            user_name, user_message, sel_response
        );

        let summary = if user_message.len() > 100 {
            format!("{}: {}...", user_name, &user_message[..97])
        } else {
            format!("{}: {}", user_name, user_message)
        };

        // Determine salience based on message characteristics
        let salience = self.calculate_salience(user_message, sel_response);

        self.store(stream_id, &content, &summary, salience).await
    }

    fn calculate_salience(&self, user_message: &str, sel_response: &str) -> f32 {
        let mut salience: f32 = 0.3; // Base salience

        // Question or important interaction
        if user_message.contains('?') {
            salience += 0.1;
        }

        // Commands or agent invocations
        if user_message.starts_with("agent:") || user_message.starts_with("bash ") {
            salience += 0.2;
        }

        // Long responses indicate important content
        if sel_response.len() > 500 {
            salience += 0.1;
        }

        // Important keywords
        let important_keywords = ["remember", "important", "don't forget", "always", "never"];
        for keyword in important_keywords {
            if user_message.to_lowercase().contains(keyword) {
                salience += 0.15;
                break;
            }
        }

        salience.min(1.0)
    }
}
