use serenity_self::model::guild::Guild;
use serenity_self::model::user::User;
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

#[derive(Debug, Clone)]
pub struct UserPresence {
    pub status: String,
    pub activities: Vec<String>,
}

pub struct PresenceTracker {
    presences: Arc<RwLock<HashMap<String, UserPresence>>>,
}

impl PresenceTracker {
    pub fn new() -> Self {
        Self {
            presences: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    pub fn update_presence(&self, user_id: String, status: String, activities: Vec<String>) {
        let mut presences = self.presences.write().unwrap();
        presences.insert(
            user_id,
            UserPresence {
                status,
                activities,
            },
        );
    }

    pub fn get_context_for_prompt(&self, limit: usize) -> String {
        let presences = self.presences.read().unwrap();

        if presences.is_empty() {
            return String::new();
        }

        let online_count = presences
            .values()
            .filter(|p| p.status == "online" || p.status == "idle" || p.status == "dnd")
            .count();

        let mut result = format!("[DISCORD PRESENCE ({} online)]\n", online_count);

        let mut entries: Vec<_> = presences.iter().take(limit).collect();
        for (user_id, presence) in entries {
            result.push_str(&format!("  • User {} ({})", user_id, presence.status));

            if !presence.activities.is_empty() {
                result.push_str(&format!(" - {}", presence.activities.join(", ")));
            }

            result.push('\n');
        }

        result.push_str("[/DISCORD PRESENCE]\n");
        result
    }

    pub fn clear(&self) {
        let mut presences = self.presences.write().unwrap();
        presences.clear();
    }
}
