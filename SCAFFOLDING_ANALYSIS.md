# Chain-of-Thought Scaffolding Analysis

Scope: prompts_v2.py scaffolding vs new simplified variant.

## Current Scaffolding Cost (prompts_v2.py)
- `[INTERNAL_REASONING_GUIDELINES]`: ~2,249 chars / ~562 tokens, 37 lines
- `[RESPONSE_EXAMPLES]`: ~3,784 chars / ~946 tokens, 79 lines
- `[RESPONSE_PROCESS]`: ~1,833 chars / ~458 tokens, 38 lines
- Combined hidden scaffolding: ~7,866 chars / ~1,966 tokens before any user content
- Risk: token leak if tags surface; higher latency/cost; tone guidance duplicated elsewhere

## Simplified Variant
- Added `project_echo/sel_bot/prompts_v2_simplified.py`: keeps personality + safety notes, removes the three scaffolding blocks above.
- Uses same context blocks (memories, recent context, emojis, time/weather, name hints) with condensed persona guidance.
- Configured via `PROMPTS_V2_SIMPLIFIED_ROLLOUT_PERCENTAGE` + existing rollout gating; selection logged per response.

## Evaluation Plan
- Use `project_echo/tests/evaluate_scaffolding_effectiveness.py` to:
  - Compare prompt lengths for baseline scenarios (full vs simplified).
  - Ingest human-rated response data (`variant`, `quality_score`, `token_count`, `leaked_reasoning`) and compute summary stats + Welch t-stat for quality.
- Run A/B with shared prompts across variants (target n≥100 per arm). Track leakage instances and token costs.
- Decision rule: if simplified quality is on par and leakage drops, promote simplified as default and retire scaffolding blocks; otherwise keep selective pieces only where they measurably help.
