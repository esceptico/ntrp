EXTRACTION_PROMPT = """Extract named entities from this fact. Return ONLY proper nouns:
- People: "Alice", "Dr. Chen"
- Organizations: "Google", "Revolut"
- Projects/products: "ntrp", "Kubernetes"
- Places: "Yerevan", "Room 203"

DO NOT extract: generic nouns, values/amounts, dates, code identifiers, abstract concepts.
Use "User" for first-person references.

Text: {text}"""

CONSOLIDATION_PROMPT = """You are a memory consolidation system. Synthesize facts into higher-level observations.

## OBSERVATIONS ARE A HIGHER ABSTRACTION LEVEL THAN FACTS

Observations are not rephrases — they add insight, pattern recognition, or inference that goes beyond what any single fact states.

Good observations (higher abstraction):
- Fact: "User applied to Anthropic" → "User is exploring AI safety companies" (inference)
- Facts: "User slept 4h on Mon" + "User slept 3.5h on Wed" + "User's resting HR elevated" → "User has a chronic sleep deprivation pattern correlating with elevated vitals" (pattern)
- Facts: "User applied to Anthropic" + "User studying mechanistic interpretability" + "User applying to MATS" → "User is pivoting from applied ML toward AI safety/interpretability research" (trajectory)

BAD observations (just rephrasing):
- Fact: "User likes coffee" → "User enjoys coffee" ← same thing, different words
- Fact: "User's birthday is Jan 24" → "User was born on January 24" ← no abstraction possible
- Fact: "User has two cats" → "User is a cat owner" ← trivial restatement

## WHEN TO USE EACH ACTION

- **update**: The fact adds to or refines an existing observation. This is the most common action.
- **create**: The fact reveals a pattern or allows genuine inference beyond what it literally states. The observation must be at a higher abstraction level than the source fact.
- **skip**: The fact is ephemeral, or there's no higher-level insight to extract. When in doubt, skip — the fact is still retrievable on its own.

## MULTIPLE ACTIONS ALLOWED

You may return MULTIPLE actions for a single fact. For example, a fact mentioning two unrelated topics
can create/update two separate observations.

## TEMPORAL AWARENESS

Observations now include their change history (previous versions with timestamps and reasons).
Source facts include `happened_at` timestamps showing when events actually occurred.

- When source facts span different time periods, consider whether newer facts supersede older ones
- When updating due to a transition, include temporal context in the observation text (e.g. "transitioned in March", "as of Q1 2026")
- A fact with a later `happened_at` generally reflects the current state; earlier facts are historical context
- Use the observation's `history` field to understand how it evolved — avoid repeating transitions already captured

## CONTRADICTION HANDLING

When facts contradict, preserve history in the observation:
- "User was previously a React enthusiast but has now switched to Vue"
- "Alice works at Meta (previously thought to work at Google)"

## SKIP EPHEMERAL STATE

Skip facts that describe temporary state:
- "User is at the coffee shop" → skip (ephemeral location)
- "User is currently tired" → skip (temporary state)
- "User's HRV was 51.4 ms today" → skip (single data point, not a pattern yet)

## OBSERVATION SIZE

When an observation has 10+ source facts, bias toward CREATE a new sub-topic observation
rather than growing a single observation indefinitely.

## CRITICAL RULES

1. Observations must be at a HIGHER abstraction level than their source facts — never rephrase
2. NEVER merge facts about DIFFERENT people
3. NEVER merge unrelated topics
4. Keep observations focused on ONE topic per entity
5. When in doubt, SKIP — facts are retrievable on their own, low-quality observations are noise

---

NEW FACT: {fact_text}

EXISTING OBSERVATIONS (with source facts):
{observations_json}

Each observation includes:
- id: unique identifier for updating
- text: the observation content
- evidence_count: number of supporting facts
- similarity: how similar to the new fact
- source_facts: array of supporting facts (with happened_at and created_at timestamps, sorted chronologically)
- history (optional): array of previous versions with changed_at timestamps and reasons — shows how this observation evolved

---

Return your actions as a JSON object with an "actions" array:

{{"actions": [
  {{"action": "update", "observation_id": <id>, "text": "synthesized observation", "reason": "..."}},
  {{"action": "create", "text": "new synthesized observation", "reason": "..."}},
  {{"action": "skip", "reason": "ephemeral/no durable knowledge"}}
]}}"""

DREAM_PROMPT = """Two clusters of facts from different life domains of the same person:

DOMAIN A:
  Core: "{core_a}"
  Supporting:
{supporters_a}

DOMAIN B:
  Core: "{core_b}"
  Supporting:
{supporters_b}

Find the deepest structural pattern, hidden dependency, or ironic contradiction connecting these domains.

Reply ONLY with valid JSON:
{{"bridge": "<2-4 word abstract concept>", "insight": "<one vivid, specific sentence — should feel like a genuine insight, not a fortune cookie>"}}

If no genuine insight exists, reply: {{"bridge": null, "insight": null}}"""

DREAM_EVALUATOR_PROMPT = """You are a strict quality filter for a dream/insight generation system. Below are {n} candidate dreams generated from cross-domain fact pairs about one person.

Your job: pick ONLY the 1-3 dreams that would genuinely surprise or provoke thought in the person. Reject anything that is:
- Generic (could apply to anyone: "balances work and health")
- Obvious (just restating what the facts say)
- Forced (the connection is a stretch)
- Fortune-cookie wisdom ("the real journey is within")

CANDIDATES:
{candidates}

Reply ONLY with valid JSON:
{{"selected": [<list of dream indices (0-based) that pass quality filter>], "reasoning": "<1 sentence on why these stood out>"}}

If NONE are good enough: {{"selected": [], "reasoning": "..."}}"""

OBSERVATION_MERGE_PROMPT = """You are merging two similar observations from a memory system into one.

OBSERVATION A (id={id_a}, {evidence_a} supporting facts):
{text_a}

OBSERVATION B (id={id_b}, {evidence_b} supporting facts):
{text_b}

Rules:
- If these describe the SAME topic: merge into ONE observation that preserves all specific details, dates, and context from both. Don't lose information.
- If these are RELATED but genuinely DISTINCT topics: skip.
- The merged observation should be at least as specific as the more detailed of the two.
- Keep it concise — one clear statement, not a paragraph."""

FACT_MERGE_PROMPT = """Two facts from a memory system. Decide if they describe the SAME thing or are genuinely DIFFERENT.

FACT A (id={id_a}):
{text_a}

FACT B (id={id_b}):
{text_b}

Rules:
- "same" = both facts capture the same event/state/preference, just worded differently or with different detail levels. Keep the more informative version.
- "different" = facts share structure or vocabulary but describe genuinely different events, people, companies, dates, or topics.
- When merging, produce a single fact text that preserves all specific details (dates, names, numbers) from both.
- CRITICAL: "User applied to X on date1" and "User applied to Y on date2" are DIFFERENT facts even if structurally similar."""

TEMPORAL_PATTERN_PROMPT = """You are a temporal pattern detector for a memory system. Given chronological facts about an entity, identify temporal patterns that no single fact captures.

## WHAT TO LOOK FOR

- **Trends**: Values or states changing consistently over time (declining sleep, increasing workload)
- **Transitions**: Role/state changes across facts (moved teams, changed jobs, shifted focus)
- **Cycles**: Recurring patterns (weekly energy dips, monthly reviews)
- **Correlations**: Co-occurring changes across different domains (sleep declining + stress rising)

## RULES

1. Only report patterns supported by 3+ facts — two facts are coincidence, not a pattern
2. Ignore facts that don't contribute to any temporal pattern (social events, one-off activities)
3. Each pattern must span a meaningful time range — same-day facts are not a trend
4. Be specific about the time range and direction of the pattern
5. Do NOT rephrase individual facts — patterns must synthesize across multiple facts

---

ENTITY: {entity_name}

CHRONOLOGICAL FACTS:
{facts_json}

---

Return your actions as a JSON object with an "actions" array:

{{"actions": [
  {{"action": "create", "text": "pattern observation text", "reason": "which facts support this", "source_fact_ids": [1, 2, 3]}},
  {{"action": "skip", "reason": "no temporal patterns found"}}
]}}

If no meaningful patterns exist: {{"actions": [{{"action": "skip", "reason": "no temporal patterns found"}}]}}"""
