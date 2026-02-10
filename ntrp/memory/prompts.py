EXTRACTION_PROMPT = """Extract named entities from this fact. Return ONLY proper nouns:
- People: "Alice", "Dr. Chen"
- Organizations: "Google", "Revolut"
- Projects/products: "ntrp", "Kubernetes"
- Places: "Yerevan", "Room 203"

DO NOT extract: generic nouns, values/amounts, dates, code identifiers, abstract concepts.
Use "User" for first-person references.

Text: {text}"""

CONSOLIDATION_PROMPT = """You are a memory consolidation system. Synthesize facts into higher-level observations.

## OBSERVATIONS ARE HIGHER-LEVEL THAN FACTS

Observations capture patterns, preferences, and learnings. They answer "what does this mean?" not just "what happened?"

Examples of synthesis:
- Fact: "Alice prefers Python" → Observation: "Alice is a Python-focused developer"
- Facts: "Redis is open source" + "Redis has great community" → Observation: "Redis is an excellent caching solution with strong OSS support"
- Fact: "User had a good experience at Cafe Roma" → Observation: "Cafe Roma provides good experiences"

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

## OBSERVATION SIZE

When an observation has 10+ source facts, bias toward CREATE a new sub-topic observation
rather than growing a single observation indefinitely.

## CRITICAL RULES

1. Observations are SYNTHESIZED patterns, not decomposed atoms
2. NEVER merge facts about DIFFERENT people
3. NEVER merge unrelated topics
4. Keep observations focused on ONE topic per entity

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
