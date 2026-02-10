import tempfile
from dataclasses import dataclass
from pathlib import Path

from ntrp.channel import Channel
from ntrp.embedder import EmbeddingConfig
from ntrp.llm import acompletion
from ntrp.memory.facts import FactMemory

from evals.data import Question, parse_date


@dataclass
class EvalConfig:
    embedding: EmbeddingConfig
    extraction_model: str
    judge_model: str
    consolidate: bool
    recall_limit: int


@dataclass
class QuestionResult:
    question: Question
    facts: list[str]
    observations: list[str]
    fact_session_ids: list[str]
    total_facts: int
    total_observations: int
    generated_answer: str


ANSWER_PROMPT = """\
You are answering a question based on your memory of past conversations with the user.
Today's date: {today}

Question: {question}

Retrieved memories:
{context}

Instructions:
- Give a short, direct answer. For factual questions, answer in one sentence.
- If the question asks for advice or recommendations, closely reference the user's specific stated preferences, past experiences, and things they explicitly want to try or move away from. Suggest things aligned with their stated interests and avoid recommending what they've expressed wanting to branch out from.
- IMPORTANT: When the question uses temporal references like "last Saturday", "recently", or "this week", first calculate the exact target date from today's date. Then strongly prefer memories dated on or near that target date. Look for language like "just", "today", or "this morning" in those memories to identify the specific event.
- When multiple memories mention different values for the same thing, use the most recent explicitly stated value — do not infer updates or do arithmetic across memories.
- Only say "I don't know" if the memories contain absolutely nothing relevant to the question.
"""


def _should_ingest(question_type: str, role: str) -> bool:
    if question_type == "single-session-assistant":
        return True
    return role == "user"


async def run_question(question: Question, config: EvalConfig) -> QuestionResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "eval.db"
        channel = Channel()

        memory = await FactMemory.create(
            db_path=db_path,
            embedding=config.embedding,
            extraction_model=config.extraction_model,
            channel=channel,
        )

        try:
            for i, (session_id, session) in enumerate(
                zip(question.haystack_session_ids, question.haystack_sessions)
            ):
                happened_at = parse_date(
                    question.haystack_dates[i]
                    if i < len(question.haystack_dates)
                    else ""
                )
                for msg in session:
                    if _should_ingest(question.question_type, msg["role"]):
                        content = msg["content"].strip()
                        if not content:
                            continue
                        await memory.remember(
                            content,
                            source_type="conversation",
                            source_ref=session_id,
                            happened_at=happened_at,
                        )

            if config.consolidate:
                while True:
                    count = await memory._consolidate_pending(batch_size=20)
                    if count == 0:
                        break

            question_time = parse_date(question.question_date)
            context = await memory.recall(
                question.question,
                limit=config.recall_limit,
                query_time=question_time,
            )

            total_facts = await memory.count()

            fact_texts = [f.text for f in context.facts]
            fact_dates = [f.happened_at for f in context.facts]
            fact_sessions = [f.source_ref or "" for f in context.facts]
            obs_texts = [o.summary for o in context.observations]

            answer = await _generate_answer(
                question.question, fact_texts, fact_dates, obs_texts,
                question.question_date, config.extraction_model,
            )

            return QuestionResult(
                question=question,
                facts=fact_texts,
                observations=obs_texts,
                fact_session_ids=fact_sessions,
                total_facts=total_facts,
                total_observations=len(context.observations),
                generated_answer=answer,
            )
        finally:
            await memory.close()


async def _generate_answer(
    question: str,
    facts: list[str],
    fact_dates: list,
    observations: list[str],
    question_date: str,
    model: str,
) -> str:
    parts = []
    if facts:
        lines = []
        for text, dt in zip(facts, fact_dates):
            date_str = dt.strftime("%Y-%m-%d") if dt else "unknown date"
            lines.append(f"- [{date_str}] {text}")
        parts.append("Facts:\n" + "\n".join(lines))
    if observations:
        parts.append(
            "Observations:\n" + "\n".join(f"- {o}" for o in observations)
        )
    context = "\n\n".join(parts) if parts else "(no memories retrieved)"

    today = question_date.split(" ")[0] if question_date else "unknown"

    response = await acompletion(
        model=model,
        messages=[
            {
                "role": "user",
                "content": ANSWER_PROMPT.format(
                    question=question, context=context, today=today,
                ),
            }
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content
