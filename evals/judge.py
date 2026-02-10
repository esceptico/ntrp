import json
from dataclasses import dataclass

from ntrp.llm import acompletion

JUDGE_PROMPT = """\
You are evaluating whether a generated answer correctly answers a question about past conversations.

Question: {question}
Expected answer: {expected}
Generated answer: {generated}

Does the generated answer contain the correct information from the expected answer? Be strict:
- The answer must contain the specific facts, not just be topically related
- For temporal questions, accept minor date/time variations
- For knowledge updates, the answer must reflect the latest information
- If the expected answer has multiple parts, all must be present

Output JSON only: {{"correct": true/false, "reasoning": "brief explanation"}}"""


@dataclass
class JudgeVerdict:
    correct: bool
    reasoning: str


async def judge(
    question: str,
    expected_answer: str,
    generated_answer: str,
    model: str,
) -> JudgeVerdict:
    prompt = JUDGE_PROMPT.format(
        question=question,
        expected=expected_answer,
        generated=generated_answer,
    )

    response = await acompletion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    parsed = json.loads(raw)

    return JudgeVerdict(
        correct=parsed["correct"],
        reasoning=parsed["reasoning"],
    )
