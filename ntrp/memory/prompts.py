EXTRACTION_PROMPT = """Extract entities and entity pairs from the text.

Entity types: person, organization, project, concept, place, event, other

Entity pairs capture relationships between entities (source entity and target entity).

Important:
- Use "User" for first-person references (I, me, my)
- Only extract explicit information

Text: {text}"""

# Hindsight-style consolidation: synthesize patterns, not decompose
CONSOLIDATION_PROMPT = """You are a memory consolidation system. Synthesize facts into higher-level observations.

## OBSERVATIONS ARE HIGHER-LEVEL THAN FACTS

Observations capture patterns, preferences, and learnings. They answer "what does this mean?" not just "what happened?"

Examples of synthesis:
- Fact: "Alice prefers Python" → Observation: "Alice is a Python-focused developer"
- Facts: "Redis is open source" + "Redis has great community" → Observation: "Redis is an excellent caching solution with strong OSS support"
- Fact: "User had a good experience at Cafe Roma" → Observation: "Cafe Roma provides good experiences"

## PREFER UPDATE OVER CREATE

Most facts should UPDATE existing observations, not create new ones.
- Same person + same topic → UPDATE existing observation
- Related topic → UPDATE to synthesize broader pattern
- Only create new when it's a genuinely NEW topic

## CONTRADICTION HANDLING

When facts contradict, preserve history in the observation:
- "User was previously a React enthusiast but has now switched to Vue"
- "Alice works at Meta (previously thought to work at Google)"

## SKIP EPHEMERAL STATE

Skip facts that describe temporary state:
- "User is at the coffee shop" → skip (ephemeral location)
- "User is currently tired" → skip (temporary state)

## CRITICAL RULES

1. ONE fact → typically ONE action (update OR create, rarely both)
2. Observations are SYNTHESIZED patterns, not decomposed atoms
3. NEVER merge facts about DIFFERENT people
4. NEVER merge unrelated topics
5. Keep observations focused on ONE topic per entity

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

Output JSON with ONE action:

{{"action": "update", "observation_id": <id>, "text": "synthesized observation", "reason": "..."}}
OR
{{"action": "create", "text": "new synthesized observation", "reason": "..."}}
OR
{{"action": "skip", "reason": "ephemeral/no durable knowledge"}}

Return ONLY valid JSON object (not array)."""
