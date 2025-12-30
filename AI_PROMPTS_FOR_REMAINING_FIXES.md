# AI Prompts for Completing Security Audit Remediation

This document contains AI-ready prompts to fix the remaining P2 issues identified in luna midori's security audit.

**Status:** 5/7 P2 issues completed. These prompts address the final 2 issues.

---

## Issue 1: Test Honesty (P2 - Quality)

### Context

**File:** `project_echo/tests/test_prompts_v2_comparison.py`

**Audit Finding:**
> "The tests claim they measure hallucinations, tone, harmful stereotypes - but they never run an LLM. That's not 'A/B testing', that's 'assert my prompt is long'. Either run actual evals with the LLM or rename these tests to admit they only validate prompt structure."

**Current State:**
- Tests named `test_v2_reduces_hallucinations()`, `test_v2_maintains_informal_tone()`, etc.
- Tests only verify prompt structure (presence of strings like "grounded responses", "don't hallucinate")
- No actual LLM execution or behavioral validation
- Misleading test names suggest they measure LLM behavior

### AI Prompt to Fix

```
You are a Python testing expert tasked with improving test honesty and clarity.

TASK: Refactor test_prompts_v2_comparison.py to accurately reflect what the tests actually validate.

CONTEXT:
The current tests claim to measure LLM behavioral outcomes (hallucinations, tone, stereotypes)
but actually only validate that certain strings/keywords exist in prompt templates. This is
misleading - the tests should be renamed to accurately describe what they test.

REQUIREMENTS:

1. READ the file: project_echo/tests/test_prompts_v2_comparison.py

2. RENAME tests to reflect structural validation, not behavioral outcomes:
   - test_v2_reduces_hallucinations() → test_v2_includes_grounding_instructions()
   - test_v2_maintains_informal_tone() → test_v2_includes_tone_guidance()
   - test_v2_avoids_harmful_stereotypes() → test_v2_includes_safety_instructions()
   - test_v2_maintains_character_consistency() → test_v2_includes_character_traits()
   - test_v2_handles_context_appropriately() → test_v2_includes_context_awareness_logic()

3. UPDATE docstrings to be honest about what is tested:
   ❌ BAD: "Verify v2 reduces hallucinations through grounded responses"
   ✅ GOOD: "Verify v2 prompt includes instructions for grounded responses"

4. ADD a comment at the top of the file:
   """
   NOTE: These tests validate PROMPT STRUCTURE, not LLM behavior.
   They verify that certain instructions/keywords are present in prompts.
   To validate actual behavioral outcomes (hallucination rates, tone, etc.),
   run LLM evals with representative test cases.
   """

5. KEEP test logic unchanged - only rename functions and update documentation

6. ENSURE all tests still pass after renaming

OUTPUT:
- Refactored test file with honest naming
- Clear separation between structural validation (current tests) and behavioral validation (future work)
- No functionality changes - only clarity improvements
```

**Expected Outcome:**
- Tests accurately named to reflect structural validation
- Clear documentation about what is/isn't tested
- Foundation for future behavioral testing if needed

---

## Issue 2: Chain-of-Thought Scaffolding Review (P2 - Quality)

### Context

**File:** `project_echo/sel_bot/prompts_v2.py`

**Audit Finding:**
> "Design smell. You bake 'internal reasoning' blocks into the prompt skeleton, but can't reliably prevent leakage (models vary), so you're paying a token tax for prose that mostly re-states 'be careful'. Either A/B test to see if it helps or simplify."

**Current State:**
- Prompts include extensive "constitutional AI" scaffolding with `<internal_reasoning>` blocks
- Instructions like "Before responding, think through...", "Consider these factors..."
- Token overhead for every request
- No validation that scaffolding improves outcomes
- Risk of scaffolding text leaking into user-visible responses

### AI Prompt to Fix

```
You are an LLM prompt engineering expert tasked with evaluating chain-of-thought scaffolding effectiveness.

TASK: Design and execute an A/B test to determine if constitutional AI scaffolding in prompts_v2.py
provides measurable value, then recommend simplification if warranted.

CONTEXT:
The current v2 prompts include extensive chain-of-thought scaffolding with <internal_reasoning> blocks
and multi-step thinking instructions. This adds token overhead and complexity. We need to determine
if this scaffolding actually improves response quality or if it can be simplified.

PHASE 1: ANALYSIS

1. READ project_echo/sel_bot/prompts_v2.py

2. IDENTIFY scaffolding components:
   - Count instances of <internal_reasoning> blocks
   - List explicit thinking instructions ("Before responding...", "Consider...")
   - Calculate token overhead (approximate: scaffolding_chars / 4)

3. DOCUMENT current scaffolding patterns:
   - Where scaffolding appears (persona building, response generation, etc.)
   - What it instructs the model to think about
   - Estimated token cost per request

PHASE 2: A/B TEST DESIGN

4. CREATE two prompt variants:

   VARIANT A (Current): Full scaffolding with <internal_reasoning> blocks
   VARIANT B (Simplified): Remove scaffolding, keep only essential instructions

   Example simplification:
   ❌ REMOVE:
   ```
   <internal_reasoning>
   Before responding, think through:
   1. What is the user really asking?
   2. What tone is appropriate given current hormones?
   3. How can I stay in character?
   </internal_reasoning>
   ```

   ✅ KEEP:
   ```
   Respond naturally in character. Current mood: {hormone_state}
   ```

5. DEFINE evaluation criteria:
   - Response quality (coherence, relevance, character consistency)
   - Response length (token efficiency)
   - Scaffolding leakage (visible <internal_reasoning> in output)
   - User engagement (if metrics available)

6. CREATE test methodology:
   - Sample size: 100 interactions per variant (200 total)
   - Use same input messages for both variants
   - Randomize variant assignment
   - Measure: quality score (1-5), token count, leakage instances

PHASE 3: IMPLEMENTATION

7. IMPLEMENT simplified prompt variant:
   - Create prompts_v2_simplified.py
   - Remove all <internal_reasoning> blocks
   - Condense multi-step instructions into direct statements
   - Preserve core personality and safety constraints

8. ADD A/B testing infrastructure:
   - Modify config.py to support prompt variant selection
   - Add prompts_v2_simplified_rollout_percentage setting
   - Log which variant was used for each response

9. CREATE evaluation script:
   - tests/evaluate_scaffolding_effectiveness.py
   - Collect responses from both variants
   - Calculate quality metrics
   - Statistical significance testing (t-test for quality scores)

PHASE 4: DECISION CRITERIA

10. ANALYZE results and recommend action:

    IF simplified variant performs equally well OR better:
    → REPLACE prompts_v2.py with simplified version
    → REMOVE scaffolding overhead (save ~100-200 tokens per request)
    → DOCUMENT in commit: "Removed chain-of-thought scaffolding after A/B test showed no quality improvement"

    IF current variant performs significantly better:
    → KEEP scaffolding
    → ADD documentation explaining why scaffolding is necessary
    → ADD safeguards to prevent leakage (strip <internal_reasoning> from output)

    IF results are mixed:
    → SELECTIVE scaffolding (keep only highest-impact instructions)
    → HYBRID approach (scaffolding for complex interactions only)

OUTPUT DELIVERABLES:

1. **Analysis Report** (SCAFFOLDING_ANALYSIS.md):
   - Current scaffolding inventory
   - Token overhead calculation
   - Leakage risk assessment

2. **Simplified Prompt Variant** (prompts_v2_simplified.py):
   - Scaffolding removed
   - Core instructions preserved
   - Estimated token savings documented

3. **A/B Testing Framework**:
   - Modified config.py with rollout control
   - Evaluation script
   - Logging infrastructure

4. **Test Results & Recommendation**:
   - Statistical analysis of both variants
   - Clear recommendation: keep, remove, or selectively simplify
   - Implementation plan for chosen approach

CONSTRAINTS:

- Do NOT remove safety instructions (sanitization, content policy)
- Do NOT remove personality/character definitions
- Do NOT change hormone system integration
- ONLY remove meta-instructions about "how to think"

TIMELINE:

Week 1: Implement variants and testing infrastructure
Week 2: Collect 200 test interactions
Week 3: Analyze results and implement chosen approach
```

**Expected Outcome:**
- Data-driven decision about scaffolding effectiveness
- Either simplified prompts (token savings) or documented justification for current approach
- Framework for future prompt optimization experiments

---

## Implementation Priority

1. **Test Honesty (Quick Win - 30 mins)**
   - Low risk, high clarity improvement
   - Pure refactoring, no behavior change
   - Can be done immediately

2. **Scaffolding Review (Research Project - 2-3 weeks)**
   - Requires A/B testing infrastructure
   - Needs user interaction data collection
   - Higher effort but potentially significant token savings

---

## Success Criteria

### Test Honesty
- ✅ All test names accurately reflect what they validate
- ✅ Docstrings clearly state "validates prompt structure, not LLM behavior"
- ✅ All tests still pass
- ✅ Future developers won't be misled about test coverage

### Scaffolding Review
- ✅ Quantified token overhead of current scaffolding
- ✅ Created and tested simplified variant
- ✅ Collected statistically significant sample (n≥100 per variant)
- ✅ Made data-driven decision with clear justification
- ✅ Implemented chosen approach with documentation

---

## Notes

**For Test Honesty:**
If you prefer even more honest naming, consider these alternatives:
- `test_v2_includes_grounding_instructions()` → `test_v2_prompt_contains_hallucination_prevention_keywords()`
- Makes it crystal clear these are string matching tests, not behavioral validation

**For Scaffolding Review:**
Alternative lightweight approach if full A/B testing is too heavy:
1. Remove scaffolding in dev environment
2. Manually test 20-30 interactions
3. Compare response quality subjectively
4. Make decision based on qualitative assessment
This is faster but less rigorous - use only if full A/B testing isn't feasible.

---

## Audit Completion Checklist

After completing these fixes:

- [x] P0: Remove RCE vulnerabilities (host_exec_api.py, tmux_control_api.py)
- [x] P0: Document git history secret leakage in README
- [x] P0: Verify docker-compose.yml security (already secure)
- [x] P1: Fix non-deterministic hash() in config.py
- [x] P1: Add clean_item() unicode sanitization function
- [x] P2: Disable fake typo injection (_add_human_touches)
- [x] P2: Add tooling (ruff, black, mypy configs)
- [x] P2: Add pre-commit hooks
- [x] P2: Add CI/CD pipeline
- [x] P2: Begin refactoring monolithic discord_client.py
- [ ] P2: Fix test honesty (rename misleading tests) ← THIS PROMPT
- [ ] P2: Review chain-of-thought scaffolding ← THIS PROMPT

**Final Status Target:** 7/7 P2 issues completed (100%)

---

**Document created:** 2025-12-29
**Audit by:** luna midori
**Remediation by:** Claude Code
**Remaining work:** Execute prompts above to complete final 2/7 P2 issues
