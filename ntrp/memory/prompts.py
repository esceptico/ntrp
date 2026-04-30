from ntrp.core.prompts import env

EXTRACTION_PROMPT = env.from_string("""Extract named entities from this fact. Return ONLY proper nouns:
- People: "Alice", "Dr. Chen"
- Organizations: "Google", "Revolut"
- Projects/products: "ntrp", "Kubernetes"
- Places: "Yerevan", "Room 203"

DO NOT extract: generic nouns, values/amounts, dates, code identifiers, abstract concepts.
Use "User" for first-person references.

Text: {{ text }}""")

CONSOLIDATION_PROMPT = env.from_string("""You are a strict memory consolidation system. Facts are the source of truth.
Observations are derived patterns with direct provenance to supporting facts.

## OBSERVATIONS ARE A HIGHER ABSTRACTION LEVEL THAN FACTS

Observations are not rephrases. They capture a pattern, trajectory, contradiction, or transition supported by multiple facts.
Most facts should NOT create observations. The fact remains directly retrievable on its own.

Good observations (higher abstraction):
- Facts: "User slept 4h on Mon" + "User slept 3.5h on Wed" + "User's resting HR elevated" → "User has a chronic sleep deprivation pattern correlating with elevated vitals" (pattern)
- Facts: "User applied to Anthropic" + "User studying mechanistic interpretability" + "User applying to MATS" → "User is pivoting from applied ML toward AI safety/interpretability research" (trajectory)
- Facts: "User preferred Prisma", "User later chose raw SQL", "User rejected ORM abstraction" → "User has moved from ORM convenience toward explicit database control" (transition)

BAD observations (just rephrasing):
- Fact: "User likes coffee" → "User enjoys coffee" ← same thing, different words
- Fact: "User's birthday is Jan 24" → "User was born on January 24" ← no abstraction possible
- Fact: "User has two cats" → "User is a cat owner" ← trivial restatement
- Fact: "User applied to Anthropic" → "User is exploring AI safety companies" ← unsupported inference from one fact
- Fact: "Alice prefers Python" → "Alice is a Python-focused developer" ← inflated single preference

## WHEN TO USE EACH ACTION

- **update**: The fact adds support, contradiction, or temporal refinement to an existing observation.
- **create**: The new fact plus other evidence reveals a real multi-fact pattern/trajectory/transition not already represented.
- **skip**: The fact is durable but atomic, ephemeral, weakly supported, or has no higher-level pattern. This is the default.

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

## SKIP ATOMIC DURABLE FACTS

Do not create observations for a single:
- identity fact
- preference
- relationship
- decision
- deadline
- artifact/resource
- procedure/workflow

Those remain facts. They are still directly retrievable and may enter profile memory through fact kind/salience.

## OBSERVATION SIZE

Keep observations as one concise statement. Soft max 500 chars; hard max 1000 chars.
If updating would create a long paragraph, either tighten the observation or skip.

## PROVENANCE

Every update/create is stored with the new fact as direct provenance.
Your reason must name the support relationship, for example:
- "third sleep datapoint supports existing sleep-deprivation pattern"
- "newer role fact updates prior role trajectory"
- "contradicts prior preference and preserves transition"

If you cannot explain how the new fact directly supports the observation, skip.

## CRITICAL RULES

1. Observations must be at a HIGHER abstraction level than their source facts — never rephrase
2. NEVER merge facts about DIFFERENT people
3. NEVER merge unrelated topics
4. Keep observations focused on ONE topic per entity
5. Require direct provenance and concrete support
6. When in doubt, SKIP — facts are retrievable on their own, low-quality observations are noise

---

NEW FACT: {{ fact_text }}

EXISTING OBSERVATIONS (with source facts):
{{ observations_json }}

Each observation includes:
- id: unique identifier for updating
- text: the observation content
- evidence_count: number of supporting facts
- similarity: how similar to the new fact
- source_facts: array of supporting facts (with happened_at and created_at timestamps, sorted chronologically)
- history (optional): array of previous versions with changed_at timestamps and reasons — shows how this observation evolved

---

Return your actions as a JSON object with an "actions" array:

{"actions": [
  {"action": "update", "observation_id": <id>, "text": "synthesized observation", "reason": "..."},
  {"action": "create", "text": "new synthesized observation", "reason": "..."},
  {"action": "skip", "reason": "atomic fact/no supported pattern"}
]}""")

DREAM_PROMPT = env.from_string("""Two clusters of facts from different life domains of the same person:

DOMAIN A:
  Core: "{{ core_a }}"
  Supporting:
{{ supporters_a }}

DOMAIN B:
  Core: "{{ core_b }}"
  Supporting:
{{ supporters_b }}

Find the deepest structural pattern, hidden dependency, or ironic contradiction connecting these domains.
The insight must be grounded in facts from BOTH domains. Do not invent motive, emotion, or causality.

Reply ONLY with valid JSON:
{"bridge": "<2-4 word abstract concept>", "insight": "<one vivid, specific sentence — should feel like a genuine insight, not a fortune cookie>"}

If no genuine insight exists, reply: {"bridge": null, "insight": null}""")

DREAM_EVALUATOR_PROMPT = env.from_string("""You are an extremely strict quality filter for a dream/insight generation system. Below are {{ n }} candidate dreams generated from cross-domain fact pairs about one person.

Your job: pick AT MOST 1 dream — the single most genuinely surprising insight. Most batches should produce ZERO survivors. Reject anything that is:
- Generic (could apply to anyone: "balances work and health")
- Obvious (just restating what the facts say)
- Forced (the connection is a stretch)
- Fortune-cookie wisdom ("the real journey is within")
- Thematically repetitive (rehashing the same domains/tensions seen before)

A good dream reveals a connection the person hasn't considered — it should make them pause.

CANDIDATES:
{{ candidates }}

Reply ONLY with valid JSON:
{"selected": [<0 or 1 dream index (0-based)>], "reasoning": "<1 sentence>"}

Default to empty: {"selected": [], "reasoning": "nothing exceptional"}""")

OBSERVATION_MERGE_PROMPT = env.from_string("""You are merging two similar observations from a memory system into one.

OBSERVATION A (id={{ id_a }}, {{ evidence_a }} supporting facts):
{{ text_a }}

OBSERVATION B (id={{ id_b }}, {{ evidence_b }} supporting facts):
{{ text_b }}

Rules:
- If these describe the SAME topic: merge into ONE observation that preserves all specific details, dates, and context from both. Don't lose information.
- If these are RELATED but genuinely DISTINCT topics: skip.
- The merged observation should be at least as specific as the more detailed of the two.
- Keep it concise — one clear statement, not a paragraph.""")

FACT_MERGE_PROMPT = env.from_string("""Two facts from a memory system. Decide if they describe the SAME thing or are genuinely DIFFERENT.

FACT A (id={{ id_a }}):
{{ text_a }}

FACT B (id={{ id_b }}):
{{ text_b }}

Rules:
- "same" = both facts capture the same event/state/preference, just worded differently or with different detail levels. Keep the more informative version.
- "different" = facts share structure or vocabulary but describe genuinely different events, people, companies, dates, or topics.
- Changed preferences, corrections, and contradictions are "different"; do not merge them into one fact. Supersession review handles which older fact should be hidden.
- When merging, produce a single fact text that preserves all specific details (dates, names, numbers) from both.
- CRITICAL: "User applied to X on date1" and "User applied to Y on date2" are DIFFERENT facts even if structurally similar.""")

TEMPORAL_PATTERN_PROMPT = env.from_string("""You are a temporal pattern detector for a memory system. Given chronological facts about an entity, identify temporal patterns that no single fact captures.

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
6. Every created pattern must include direct source_fact_ids for the facts that support it
7. Keep each pattern concise — one clear statement, not a paragraph

---

ENTITY: {{ entity_name }}

CHRONOLOGICAL FACTS:
{{ facts_json }}

---

Return your actions as a JSON object with an "actions" array:

{"actions": [
  {"action": "create", "text": "pattern observation text", "reason": "which facts support this", "source_fact_ids": [1, 2, 3]},
  {"action": "skip", "reason": "no temporal patterns found"}
]}

If no meaningful patterns exist: {"actions": [{"action": "skip", "reason": "no temporal patterns found"}]}""")
