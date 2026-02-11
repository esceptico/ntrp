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
- source_facts: array of supporting facts

---

Output a JSON ARRAY of actions:

[
  {{"action": "update", "observation_id": <id>, "text": "synthesized observation", "reason": "..."}},
  {{"action": "create", "text": "new synthesized observation", "reason": "..."}},
  {{"action": "skip", "reason": "ephemeral/no durable knowledge"}}
]

Return ONLY valid JSON array."""
