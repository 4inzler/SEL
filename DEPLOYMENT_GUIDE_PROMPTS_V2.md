# Deployment Guide: Prompts V2 Enhanced LLM System

## Overview

This guide covers the staged rollout of the enhanced prompts_v2.py system with constitutional AI and chain-of-thought reasoning.

**What changed:**
- Added invisible quality guardrails (factual grounding, uncertainty calibration, consistency checks)
- Implemented few-shot examples demonstrating personality + accuracy
- Built cognitive scaffolding for systematic reasoning
- Preserved Sel's authentic conversational voice

**Token overhead:** ~3.4x more tokens (~1750 vs ~500), but quality improvements justify cost.

## Quick Rollback

If you need to immediately disable v2:

```bash
# Set in .env file
ENABLE_PROMPTS_V2=false

# Then restart the bot
docker-compose restart sel-service
```

Or via environment variable:
```bash
ENABLE_PROMPTS_V2=false poetry run python -m sel_bot.main
```

## Staged Rollout Strategy

### Phase 1: Alpha Testing (Internal - 5% traffic)

**Goal:** Verify no regressions, basic quality improvements visible

1. Enable v2 for 5% of channels:
   ```bash
   # .env
   ENABLE_PROMPTS_V2=true
   PROMPTS_V2_ROLLOUT_PERCENTAGE=5
   ```

2. Monitor for 24 hours:
   - Check logs for errors related to prompts
   - Observe responses in test channels
   - Look for any personality regression

3. Success criteria:
   - No crashes or errors
   - Responses still sound like Sel
   - At least one instance of improved behavior (better uncertainty, structure compliance, etc.)

**Rollback trigger:** Any crashes or major personality changes

### Phase 2: Beta Testing (20% traffic)

**Goal:** Gather statistically significant quality data

1. Increase rollout:
   ```bash
   # .env
   PROMPTS_V2_ROLLOUT_PERCENTAGE=20
   ```

2. Monitor for 3-7 days:
   - Collect user feedback (reactions, corrections)
   - Compare factual accuracy between v1 and v2 channels
   - Measure format compliance for structured requests

3. Success criteria:
   - User satisfaction maintained or improved
   - Hallucination rate same or lower
   - No increase in correction rate

**Rollback trigger:** User complaints increase >10%, or hallucinations increase

### Phase 3: Canary Release (50% traffic)

**Goal:** Confirm scalability and broad compatibility

1. Increase to half of traffic:
   ```bash
   # .env
   PROMPTS_V2_ROLLOUT_PERCENTAGE=50
   ```

2. Monitor for 7 days:
   - Track token costs (expect ~3.4x increase)
   - Monitor LLM API latency
   - Check for edge cases in diverse channels

3. Success criteria:
   - Cost increase acceptable (3-4x tokens)
   - No latency degradation
   - Quality improvements consistent across channel types

**Rollback trigger:** Cost unsustainable, or latency issues

### Phase 4: Full Deployment (100% traffic)

**Goal:** Complete migration to enhanced prompts

1. Enable for all channels:
   ```bash
   # .env
   PROMPTS_V2_ROLLOUT_PERCENTAGE=100
   ```

2. Monitor for 14 days before considering permanent

3. After stable period, can remove v1 code:
   - Keep prompts.py as `prompts_legacy.py` for historical reference
   - Rename prompts_v2.py to prompts.py
   - Remove feature flag logic

**Rollback trigger:** Major unforeseen issue

## Monitoring Metrics

### Key Performance Indicators

**Quality Metrics:**
- **Hallucination rate:** Manual review of 50 responses/week, check factual errors
- **Format compliance:** Test structured requests (lists, steps), measure compliance %
- **Uncertainty calibration:** Check if Sel admits uncertainty appropriately
- **Consistency:** Look for contradictions within conversations

**Operational Metrics:**
- **Token usage:** Track input tokens per message (expect 3-4x increase)
- **Cost:** Monitor OpenRouter bills (should scale with token increase)
- **Latency:** Track response generation time (may increase slightly with larger prompts)
- **Error rate:** Watch for LLM errors or timeout issues

**User Experience:**
- **Reaction sentiment:** Track 👍 vs 👎 reactions
- **Correction rate:** Count "actually..." or "no..." follow-ups
- **Engagement:** Messages per conversation, average conversation length

### Logging for A/B Comparison

The system logs which prompt version is used for each response. To analyze:

```bash
# Check which channels are using v2
grep "should_use_prompts_v2" logs/sel.log

# Compare response quality by version
# (This would require custom analysis script)
```

## Rollback Procedures

### Immediate Rollback (Emergency)

If critical issue detected:

```bash
# 1. Disable v2 completely
ENABLE_PROMPTS_V2=false

# 2. Restart service
docker-compose restart sel-service

# 3. Verify rollback
# Check that responses no longer include INTERNAL_REASONING_GUIDELINES
```

**Recovery time:** <1 minute

### Gradual Rollback (Quality Issues)

If quality problems emerge:

```bash
# 1. Reduce rollout percentage
PROMPTS_V2_ROLLOUT_PERCENTAGE=5  # or 0

# 2. Investigate root cause
# 3. Fix and re-test
# 4. Resume gradual rollout
```

### Permanent Reversion (V2 Failed)

If v2 proves unsuccessful:

1. Set `ENABLE_PROMPTS_V2=false` permanently
2. Document lessons learned
3. Remove v2 code in next release:
   ```bash
   git rm project_echo/sel_bot/prompts_v2.py
   # Remove feature flag from config.py
   # Remove imports from discord_client.py
   ```

## Testing Checklist

Before each rollout phase, test:

- [ ] Factual technical question (e.g., "How does DNS work?")
- [ ] Unknown topic question (should admit uncertainty)
- [ ] Structured output request (e.g., "List the differences between X and Y")
- [ ] Casual conversation (should maintain personality)
- [ ] Serious debugging request (should show empathy + help)
- [ ] Follow-up referencing prior context (should maintain consistency)

## Cost Analysis

**Token usage increase:** ~3.4x (from ~500 to ~1750 tokens per request)

**Estimated cost impact:**
- Claude Sonnet 3.5: $3/M input tokens
- Baseline cost: 500 tokens × $3/M = $0.0015/request
- V2 cost: 1750 tokens × $3/M = $0.00525/request
- Increase: +$0.00375/request (~3.5x)

For a bot processing 10,000 requests/day:
- Baseline: $15/day
- V2: $52.50/day
- Increase: +$37.50/day (+$1125/month)

**ROI justification:**
- Reduced hallucinations → fewer user corrections → time saved
- Better format compliance → more useful responses
- Improved uncertainty calibration → higher trust

## Advanced Configuration

### Per-Channel Override

To force specific channels to always use v2 (or v1):

```python
# In discord_client.py, modify should_use_prompts_v2 check:

# Force v2 for specific channel
if str(message.channel.id) == "IMPORTANT_CHANNEL_ID":
    build_messages = build_messages_v2
else:
    build_messages = build_messages_v2 if self.settings.should_use_prompts_v2(str(message.channel.id)) else build_messages_v1
```

### Custom Rollout Strategy

The deterministic hash-based rollout ensures channels consistently get the same version. To change assignment:

```python
# In config.py:should_use_prompts_v2()
# Current: channel_hash = hash(channel_id) % 100

# Alternative: Time-based rotation (change assignment daily)
from datetime import datetime
day_of_year = datetime.now().timetuple().tm_yday
channel_hash = (hash(channel_id) + day_of_year) % 100
```

## Troubleshooting

### Issue: "Responses too formal/robotic"

**Cause:** Constitutional principles overwhelming personality

**Fix:** Edit prompts_v2.py constitutional layer:
```python
# Reduce emphasis on formality, reinforce casualness
"These checks happen IN YOUR HEAD. Output still sounds like you, just... better grounded."
# Add more reminders to stay casual
```

### Issue: "Token limit exceeded"

**Cause:** V2 prompts + long context exceeding model limit

**Fix:**
1. Reduce `RECENT_CONTEXT_LIMIT` from 20 to 15
2. Reduce `MEMORY_RECALL_LIMIT` from 10 to 7
3. Streamline few-shot examples in prompts_v2.py

### Issue: "No noticeable quality improvement"

**Cause:** Model not following constitutional principles

**Fix:**
1. Test with different models (try Opus 4.5 instead of Sonnet 3.5)
2. Increase temperature slightly to avoid over-rigid responses
3. Add more explicit examples demonstrating desired behavior

### Issue: "Costs higher than expected"

**Cause:** Prompt caching not working, or more traffic than estimated

**Fix:**
1. Verify response cache is enabled (`llm_client.enable_cache=True`)
2. Check cache hit rate: `/sel_cache_stats` slash command
3. Consider reducing v2 rollout percentage

## Post-Deployment Review

After 30 days at 100% rollout, conduct comprehensive review:

### Quantitative Analysis
- Compare hallucination rate (before vs after)
- Measure format compliance improvement
- Calculate actual cost increase
- Review user reaction sentiment trends

### Qualitative Analysis
- Collect user feedback via survey
- Review most upvoted/downvoted responses
- Identify remaining failure modes
- Document unexpected behaviors (good and bad)

### Decision Point
- **Success:** Archive prompts.py, make v2 permanent
- **Partial success:** Iterate on v2, deploy v3
- **Failure:** Revert to v1, document lessons learned

## Next Iteration (V3 planning)

Based on v2 learnings, potential improvements:

1. **Dynamic scaffolding:** Adjust reasoning depth based on question complexity
2. **User-specific tuning:** Adapt constitutional principles per user preferences
3. **Metacognitive monitoring:** Self-assess confidence and request clarification
4. **Retrieval-augmented grounding:** Fetch external sources for facts
5. **Multi-step reasoning:** Explicit chain-of-thought for complex questions

## Support

Questions or issues during rollout?
- Review this guide
- Check test suite: `pytest tests/test_prompts_v2_comparison.py -v`
- Examine sample outputs: `python -c "from tests.test_prompts_v2_comparison import print_comparison_for_manual_review; print_comparison_for_manual_review()"`
- Consult CLAUDE.md for development guidelines

Remember: The goal is to make Sel more helpful and reliable while keeping the authentic personality that makes Sel... Sel.
