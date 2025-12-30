# Prompts V2: Quick Reference Guide

## What is Prompts V2?

Enhanced LLM prompt system for Sel that adds:
- **Constitutional AI**: Self-correction principles for factual grounding
- **Chain-of-thought scaffolding**: Systematic reasoning framework
- **Few-shot examples**: Concrete demonstrations of quality responses
- **Personality preservation**: Sel still sounds casual and authentic

## Enable/Disable

### Enable for all channels:
```bash
# .env
ENABLE_PROMPTS_V2=true
PROMPTS_V2_ROLLOUT_PERCENTAGE=100
```

### Gradual rollout (20% of channels):
```bash
# .env
ENABLE_PROMPTS_V2=true
PROMPTS_V2_ROLLOUT_PERCENTAGE=20
```

### Disable completely:
```bash
# .env
ENABLE_PROMPTS_V2=false
```

### Emergency rollback:
```bash
ENABLE_PROMPTS_V2=false docker-compose restart sel-service
```

## Key Improvements

| Aspect | V1 (Original) | V2 (Enhanced) |
|--------|---------------|---------------|
| **Factual accuracy** | No explicit grounding | Constitutional principles for fact-checking |
| **Uncertainty** | May guess when unsure | Calibrated confidence expressions |
| **Format compliance** | Casual bias may ignore structure | Balances structure + personality |
| **Consistency** | Implicit memory reference | Explicit context checking |
| **Tone matching** | Fixed casualness | Adapts to user's formality |
| **Token usage** | ~500 tokens/request | ~1750 tokens/request (3.4x) |

## Testing

Run automated tests:
```bash
cd project_echo
poetry run pytest tests/test_prompts_v2_comparison.py -v
```

Manual comparison (see prompts side-by-side):
```bash
python -c "from tests.test_prompts_v2_comparison import print_comparison_for_manual_review; print_comparison_for_manual_review()"
```

Test scenarios to verify quality:
1. **Factual question:** "How does TCP congestion control work?"
   - V2 should provide accurate technical content with casual tone
2. **Unknown topic:** "What's new in Zig 0.13?"
   - V2 should admit uncertainty casually ("not sure but...")
3. **Structured request:** "List main features of Rust"
   - V2 should provide bullet points with commentary
4. **Casual chat:** "what music you listening to?"
   - V2 should maintain Sel's authentic voice
5. **Serious help:** "I'm stuck debugging a segfault"
   - V2 should prioritize empathy + practical help

## Monitoring

Check which version a channel is using:
```python
from sel_bot.config import Settings
settings = Settings()
channel_id = "123456789"
is_v2 = settings.should_use_prompts_v2(channel_id)
print(f"Channel {channel_id}: {'v2' if is_v2 else 'v1'}")
```

Monitor responses for quality:
- Look for `[INTERNAL_REASONING_GUIDELINES]` in system messages (v2 only)
- Check that responses still sound casual despite scaffolding
- Watch for improved structure compliance
- Verify uncertainty is expressed appropriately

## Cost Impact

**Token increase:** ~3.4x (500 → 1750 tokens per request)

**Monthly cost estimate** (10,000 requests/day):
- V1: ~$450/month
- V2: ~$1,575/month
- Increase: +$1,125/month

Offset by:
- Fewer user corrections (time saved)
- Higher quality responses (better UX)
- Reduced hallucination rate (trust increase)

## Troubleshooting

### "Responses sound too formal"
**Fix:** V2 over-emphasizing structure. Edit `prompts_v2.py` constitutional layer to reinforce casualness.

### "Token limits exceeded"
**Fix:** Reduce `RECENT_CONTEXT_LIMIT` (20→15) and `MEMORY_RECALL_LIMIT` (10→7) in settings.

### "No quality difference"
**Fix:**
1. Try different model (Opus instead of Sonnet)
2. Increase temperature slightly
3. Add more explicit few-shot examples

### "Costs too high"
**Fix:**
1. Verify cache is working (`/sel_cache_stats` command)
2. Reduce rollout percentage
3. Consider v2 only for important channels

## Files Changed

**New files:**
- `sel_bot/prompts_v2.py` - Enhanced prompt builder
- `tests/test_prompts_v2_comparison.py` - A/B test suite
- `DEPLOYMENT_GUIDE_PROMPTS_V2.md` - Full deployment docs
- `PROMPTS_V2_QUICK_REFERENCE.md` - This file

**Modified files:**
- `sel_bot/config.py` - Added feature flags
- `sel_bot/discord_client.py` - Integrated v2 prompts with flag

**Unchanged:**
- `sel_bot/prompts.py` - Original prompts (v1 baseline)
- `sel_bot/hormones.py` - Hormonal system unchanged
- `sel_bot/behaviour.py` - Response logic unchanged

## Rollout Recommendation

**Recommended path:**
1. **Week 1:** 5% rollout, monitor for errors
2. **Week 2-3:** 20% rollout, gather quality data
3. **Week 4-5:** 50% rollout, verify scalability
4. **Week 6+:** 100% rollout, monitor stability

**Success criteria:**
- No increase in crashes/errors
- Hallucination rate same or lower
- User satisfaction maintained/improved
- Personality still recognizably "Sel"

## Quick Commands

```bash
# Enable v2 for testing
ENABLE_PROMPTS_V2=true PROMPTS_V2_ROLLOUT_PERCENTAGE=5 poetry run python -m sel_bot.main

# Run test suite
poetry run pytest tests/test_prompts_v2_comparison.py -v

# Check token usage
poetry run pytest tests/test_prompts_v2_comparison.py::TestPromptTokenEfficiency -v -s

# View example prompts
python -c "from tests.test_prompts_v2_comparison import print_comparison_for_manual_review; print_comparison_for_manual_review()"

# Immediate rollback
ENABLE_PROMPTS_V2=false docker-compose restart sel-service
```

## Next Steps

After successful v2 deployment, consider:
- **Dynamic scaffolding**: Adjust reasoning depth based on complexity
- **User-specific tuning**: Adapt principles to user preferences
- **RAG integration**: Ground facts with external sources
- **Metacognitive monitoring**: Self-assess and request clarification
- **Multi-step CoT**: Explicit reasoning for complex questions

## Support

- Full documentation: `DEPLOYMENT_GUIDE_PROMPTS_V2.md`
- Development guide: `CLAUDE.md`
- Test suite: `tests/test_prompts_v2_comparison.py`
- Questions: Check deployment guide troubleshooting section
