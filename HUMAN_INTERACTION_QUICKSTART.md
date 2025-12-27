# Quick Start: Using the Human-Like SEL

## What Changed

SEL now talks like a real person texting you, not an AI assistant. Here's how to use it:

## Starting the Bot

```bash
cd project_echo
poetry install
poetry run python -m sel_bot.main
```

Make sure you have these environment variables set:
```bash
export DISCORD_BOT_TOKEN="your_token_here"
export OPENROUTER_API_KEY="your_key_here"
```

## Example Conversations

### Before vs After

**Technical Question:**
```
❌ Before: "Great question! Async/await in Python allows..."
✅ Now: "oh so basically it lets you do multiple things at once without threading..."
```

**When Uncertain:**
```
❌ Before: "I believe it was released in 2023, though I'm not certain."
✅ Now: "uh 2023 i think? october maybe? idk im not totally sure tho"
```

**Enthusiasm:**
```
❌ Before: "That's wonderful news! Congratulations! 🎉"
✅ Now: "wait WHAT thats huge!! congrats omg"
```

**Just Chatting:**
```
❌ Before: "I understand you're feeling burnt out. Have you considered..."
✅ Now: "yeah i feel that. burnouts rough... you been getting any breaks?"
```

## Key Differences You'll Notice

### 1. Natural Typing Style
- Lowercase when casual: "i think", "thats cool", "yeah"
- Contractions: "dont", "cant", "shouldve", "gonna", "wanna"
- Fragments: "not sure.", "maybe?", "yeah"
- Natural reactions: "oh shit", "wait what", "lmao", "oof"

### 2. Emotional Authenticity
- Admits uncertainty: "i think?", "not totally sure"
- Shows genuine moods based on hormone state
- Can be tired, energetic, overwhelmed, chill
- Not always helpful or available

### 3. Real Conversational Flow
- Matches your energy naturally
- Doesn't over-explain
- Can change topics or go off on tangents
- References past conversations naturally

### 4. No AI-isms
- Won't say "I'm thinking" or "Let me consider"
- Won't apologize reflexively
- Won't offer help unprompted ("let me know if you need anything")
- Won't use assistant language ("certainly", "I'd be happy to")

## Testing Tips

### Good Conversations to Try

1. **Quick chat**: "hey whats up"
   - Should get brief, natural response

2. **Ask something technical**: "how does docker work"
   - Should explain like a person, not a manual

3. **Ask about something obscure**: "whats the latest chromium build number"
   - Should admit not knowing honestly

4. **Share good news**: "I JUST GOT PROMOTED"
   - Should match your excitement

5. **Vent about something**: "ugh my code keeps breaking"
   - Should empathize, not immediately try to fix

6. **Return after silence**: (wait a day, then message)
   - Should acknowledge the gap naturally

### What Good Looks Like

✅ Natural pacing (brief responses to brief messages)  
✅ Genuine uncertainty when appropriate  
✅ Matching your energy level  
✅ Casual language without trying too hard  
✅ References to past conversations  
✅ Moods that change based on hormone state  
✅ Fragments and informal grammar  

### Red Flags (Report These)

❌ Too polished or formal  
❌ Reflexive apologies  
❌ Offering help unprompted  
❌ Using "certainly", "I'd be happy to"  
❌ Explaining itself too much  
❌ Sign-offs like "hope this helps"  

## Hormone-Based Moods

SEL's responses change based on emotional state:

- **"kinda overwhelmed"** → More direct, less chatty
- **"pretty chill"** → Relaxed, easygoing responses
- **"energetic"** → More engaged, enthusiastic
- **"a bit drained"** → Shorter, tiredness showing
- **"curious about things"** → Asks follow-ups
- **"pretty upbeat"** → Positive, cheerful tone
- **"not super patient rn"** → More direct, less tolerance for nonsense

You'll see these moods naturally reflected in how SEL talks.

## Advanced: Using Prompts V2

Enable enhanced prompts with cognitive scaffolding:

```bash
# In your .env or environment
export PROMPTS_V2_CHANNEL_IDS="channel_id_1,channel_id_2"
```

Prompts V2 adds:
- Constitutional AI self-checking
- Few-shot examples
- Cognitive scaffolding

But the human-like voice is the same.

## Rollback (If Needed)

The changes are prompt-level only. If you need to temporarily revert:

1. Keep a backup of the old prompts
2. Swap back in `prompts.py` and `prompts_v2.py`
3. Restart the bot

## Monitoring

Watch for:
- User engagement (should increase)
- Conversation naturalness
- Technical accuracy (should not decrease)
- Appropriate tone in different contexts

## Common Questions

**Q: Will SEL make typos?**  
A: Extremely rarely (< 5% of messages), and only subtle ones like "thats" instead of "that's". Never breaks readability.

**Q: Can I control the casualness level?**  
A: Yes, through the global personality settings (teasing_level, confidence, etc.) and user preferences in USER_PROFILE.

**Q: Will SEL still be helpful with technical questions?**  
A: Yes! The explanation style is conversational but the content is still accurate. Example: "so basically async/await lets you do multiple things at once..." is still technically correct.

**Q: What if a user prefers formal communication?**  
A: SEL respects USER_PROFILE preferences. Set `prefers_short_replies`, `emoji_preference`, and `likes_teasing` appropriately.

**Q: Can SEL be serious when needed?**  
A: Absolutely. When users are struggling, venting, or discussing serious topics, SEL adjusts tone appropriately. The casualness doesn't mean frivolousness.

## Troubleshooting

### SEL seems too casual for professional channels
- Adjust `global_state.confidence` higher
- Set channel-specific user preferences
- Consider using style hints in the message context

### SEL isn't showing personality
- Check hormone levels (they affect mood expression)
- Verify you're not using very old cached responses
- Make sure recent_context is being provided

### Responses feel inconsistent
- This is intentional! Real people are inconsistent
- However, if it's jarring, check hormone decay rates
- Ensure memory system is working (maintains continuity)

## Support

For issues or questions:
1. Check `/workspace/HUMAN_INTERACTION_OVERHAUL.md` for full technical details
2. Review hormone states with `/sel_status` slash command
3. Check logs for classification and mood data

## Final Note

The goal is for you to forget you're talking to a bot. If you find yourself thinking "wow this feels like texting a real person", it's working perfectly.
