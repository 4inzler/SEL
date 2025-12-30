use anyhow::{Context, Result};
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::Arc;
use tokio::process::Command;

use crate::config::Config;

pub struct AgentManager {
    config: Arc<Config>,
}

impl AgentManager {
    pub fn new(config: Arc<Config>) -> Self {
        Self { config }
    }

    pub async fn run_agent(&self, agent_name: &str, query: &str) -> Result<String> {
        // For now, call Python agents via subprocess
        // Future: could support native Rust agents
        let agents_dir = PathBuf::from(&self.config.agents_dir);
        let agent_path = agents_dir.join(format!("{}.py", agent_name));

        if !agent_path.exists() {
            anyhow::bail!("Agent '{}' not found at {:?}", agent_name, agent_path);
        }

        // Execute Python agent using .venv/Scripts/python.exe
        let python_exe = if cfg!(windows) {
            ".venv/Scripts/python.exe"
        } else {
            ".venv/bin/python"
        };

        let output = Command::new(python_exe)
            .arg("-c")
            .arg(format!(
                r#"
import sys
sys.path.insert(0, '.')
from agents import {} as agent
result = agent.run('{}')
print(result)
"#,
                agent_name,
                query.replace('\'', "\\'")
            ))
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output()
            .await
            .context("Failed to execute agent")?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            anyhow::bail!("Agent execution failed: {}", stderr);
        }

        let result = String::from_utf8_lossy(&output.stdout).to_string();
        Ok(result.trim().to_string())
    }

    pub fn detect_agent_invocation(&self, message: &str) -> Option<(String, String)> {
        // Check for explicit agent invocation: "agent:name query"
        if message.starts_with("agent:") {
            let parts: Vec<&str> = message.splitn(2, ' ').collect();
            if parts.len() == 2 {
                let agent_name = parts[0].trim_start_matches("agent:").to_string();
                let query = parts[1].to_string();
                return Some((agent_name, query));
            } else if parts.len() == 1 {
                let agent_name = parts[0].trim_start_matches("agent:").to_string();
                return Some((agent_name, String::new()));
            }
        }

        // Check for bash command shortcuts
        if message.starts_with("bash ") || message.starts_with("run command ") {
            let query = message
                .trim_start_matches("bash ")
                .trim_start_matches("run command ")
                .to_string();
            return Some(("system_agent".to_string(), query));
        }

        None
    }

    pub async fn classify_and_maybe_invoke(
        &self,
        message: &str,
        user_id: &str,
        llm_client: &crate::llm_client::LlmClient,
    ) -> Option<(String, String)> {
        // Only classify for approved users
        if user_id != self.config.approval_user_id {
            return None;
        }

        let intent = llm_client
            .classify_intent(message, user_id, &self.config.approval_user_id)
            .await
            .ok()?;

        if intent == "system" {
            Some(("system_agent".to_string(), message.to_string()))
        } else {
            None
        }
    }
}
