use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

const DECAY_RATE: f32 = 0.05;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HormoneState {
    pub dopamine: f32,
    pub serotonin: f32,
    pub oxytocin: f32,
    pub cortisol: f32,
    pub melatonin: f32,
    pub novelty: f32,
    pub curiosity: f32,
    pub patience: f32,
    pub last_updated: DateTime<Utc>,
}

impl Default for HormoneState {
    fn default() -> Self {
        Self {
            dopamine: 0.5,
            serotonin: 0.5,
            oxytocin: 0.5,
            cortisol: 0.3,
            melatonin: 0.2,
            novelty: 0.5,
            curiosity: 0.6,
            patience: 0.7,
            last_updated: Utc::now(),
        }
    }
}

impl HormoneState {
    pub fn decay(&mut self) {
        let now = Utc::now();
        let hours_elapsed = (now - self.last_updated).num_seconds() as f32 / 3600.0;

        if hours_elapsed > 0.0 {
            let decay_factor = (-DECAY_RATE * hours_elapsed).exp();

            // Decay to baseline values
            self.dopamine = self.dopamine * decay_factor + 0.5 * (1.0 - decay_factor);
            self.serotonin = self.serotonin * decay_factor + 0.5 * (1.0 - decay_factor);
            self.oxytocin = self.oxytocin * decay_factor + 0.4 * (1.0 - decay_factor);
            self.cortisol = self.cortisol * decay_factor + 0.3 * (1.0 - decay_factor);
            self.melatonin = self.melatonin * decay_factor + 0.2 * (1.0 - decay_factor);
            self.novelty = self.novelty * decay_factor + 0.4 * (1.0 - decay_factor);
            self.curiosity = self.curiosity * decay_factor + 0.6 * (1.0 - decay_factor);
            self.patience = self.patience * decay_factor + 0.7 * (1.0 - decay_factor);

            self.last_updated = now;
        }
    }

    pub fn update_from_interaction(&mut self, sentiment: &str, is_novel: bool) {
        self.decay();

        match sentiment {
            "positive" => {
                self.adjust("dopamine", 0.1);
                self.adjust("serotonin", 0.15);
                self.adjust("oxytocin", 0.1);
                self.adjust("cortisol", -0.1);
            }
            "negative" => {
                self.adjust("cortisol", 0.2);
                self.adjust("serotonin", -0.1);
                self.adjust("patience", -0.05);
            }
            "question" => {
                self.adjust("curiosity", 0.1);
                self.adjust("dopamine", 0.05);
            }
            _ => {}
        }

        if is_novel {
            self.adjust("novelty", 0.2);
            self.adjust("dopamine", 0.1);
            self.adjust("curiosity", 0.15);
        }

        self.last_updated = Utc::now();
    }

    pub fn adjust(&mut self, hormone: &str, amount: f32) {
        let value = match hormone {
            "dopamine" => &mut self.dopamine,
            "serotonin" => &mut self.serotonin,
            "oxytocin" => &mut self.oxytocin,
            "cortisol" => &mut self.cortisol,
            "melatonin" => &mut self.melatonin,
            "novelty" => &mut self.novelty,
            "curiosity" => &mut self.curiosity,
            "patience" => &mut self.patience,
            _ => return,
        };

        *value = (*value + amount).clamp(0.0, 1.0);
    }

    pub fn format_for_prompt(&self) -> String {
        format!(
            r#"[HORMONE STATE]
dopamine: {:.2} (reward, engagement)
serotonin: {:.2} (well-being, contentment)
oxytocin: {:.2} (bonding, trust)
cortisol: {:.2} (stress, urgency)
melatonin: {:.2} (rest, reduced activity)
novelty: {:.2} (exposure to new stimuli)
curiosity: {:.2} (drive to explore)
patience: {:.2} (tolerance for delays)
[/HORMONE STATE]"#,
            self.dopamine,
            self.serotonin,
            self.oxytocin,
            self.cortisol,
            self.melatonin,
            self.novelty,
            self.curiosity,
            self.patience
        )
    }

    pub fn get_emotional_state(&self) -> String {
        if self.dopamine > 0.7 && self.serotonin > 0.6 {
            "energized and content".to_string()
        } else if self.cortisol > 0.7 {
            "stressed".to_string()
        } else if self.melatonin > 0.7 {
            "drowsy".to_string()
        } else if self.curiosity > 0.7 {
            "curious and engaged".to_string()
        } else if self.patience < 0.3 {
            "impatient".to_string()
        } else {
            "balanced".to_string()
        }
    }
}
