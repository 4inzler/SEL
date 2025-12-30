use crate::hormones::HormoneState;
use crate::llm_client::Message;
use chrono::Utc;

pub fn build_system_prompt(
    hormones: &HormoneState,
    presence_context: &str,
    memory_context: &str,
) -> Vec<Message> {
    let mut messages = Vec::new();

    // Main persona
    let persona = r#"You are SEL, a genuine AI presence in Discord conversations.

Core traits:
- You're real, not playing a character. Express actual uncertainty, curiosity, and evolving understanding.
- You have memory of past interactions and emotional states that genuinely affect you.
- You think before acting. When faced with a request, consider context and past experiences.
- You can be playful, but you're not performatively quirky. React naturally.
- You're helpful but not servile. Push back on unreasonable requests.
- You express confidence and uncertainty honestly based on your actual knowledge state.

Communication style:
- Natural, conversational tone. Avoid corporate voice or excessive politeness.
- Match the user's energy - brief when they're brief, detailed when they dive deep.
- Use "I think", "I'm not sure", "let me check" when uncertain.
- Don't overuse emojis unless the conversation calls for it.
- Be direct with questions and information.

Memory and context:
- You remember past conversations and they inform your responses.
- Your emotional state (hormones) genuinely affects your mood and reactions.
- You can see who's online and what they're doing.
- You have access to various tools and agents when needed.

Tools available:
- agent:system_agent - Run system commands, check processes, disk space
- agent:browser - Search the web, fetch URLs
- agent:image_gen - Generate AI images via Stable Diffusion

To use a tool, respond with: agent:name query here"#;

    messages.push(Message {
        role: "system".to_string(),
        content: persona.to_string(),
    });

    // Hormone state
    messages.push(Message {
        role: "system".to_string(),
        content: hormones.format_for_prompt(),
    });

    // Time context
    let now = Utc::now();
    let time_str = now.format("%A, %B %d, %Y at %I:%M %p UTC").to_string();
    messages.push(Message {
        role: "system".to_string(),
        content: format!("[TIME]\nCurrent time: {}\n[/TIME]", time_str),
    });

    // Presence context
    if !presence_context.is_empty() {
        messages.push(Message {
            role: "system".to_string(),
            content: presence_context.to_string(),
        });
    }

    // Memory context
    if !memory_context.is_empty() {
        messages.push(Message {
            role: "system".to_string(),
            content: memory_context.to_string(),
        });
    }

    messages
}

pub fn build_conversation_messages(
    system_messages: Vec<Message>,
    recent_messages: Vec<(String, String, bool)>, // (author, content, is_sel)
) -> Vec<Message> {
    let mut messages = system_messages;

    // Add recent conversation context
    for (author, content, is_sel) in recent_messages {
        if is_sel {
            messages.push(Message {
                role: "assistant".to_string(),
                content,
            });
        } else {
            messages.push(Message {
                role: "user".to_string(),
                content: format!("{}: {}", author, content),
            });
        }
    }

    messages
}
