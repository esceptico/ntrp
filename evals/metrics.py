from dataclasses import dataclass


@dataclass
class RetrievalMetrics:
    recall_all: float  # 1.0 if ALL gold sessions covered, else 0.0
    session_recall: float  # fraction of gold sessions covered
    fact_precision: float  # fraction of retrieved facts from gold sessions
    sessions_covered: int
    gold_sessions: int
    total_facts: int
    facts_retrieved: int
    facts_from_gold: int
    selectivity: float  # facts_retrieved / total_facts


def compute_retrieval_metrics(
    retrieved_session_ids: list[str],
    gold_session_ids: list[str],
    total_facts: int,
    facts_retrieved: int,
) -> RetrievalMetrics:
    gold = set(gold_session_ids)

    if not gold:
        return RetrievalMetrics(
            recall_all=1.0,
            session_recall=1.0,
            fact_precision=1.0 if not retrieved_session_ids else 0.0,
            sessions_covered=0,
            gold_sessions=0,
            total_facts=total_facts,
            facts_retrieved=facts_retrieved,
            facts_from_gold=0,
            selectivity=facts_retrieved / total_facts if total_facts else 0,
        )

    retrieved_set = set(s for s in retrieved_session_ids if s)
    covered = retrieved_set & gold
    session_recall = len(covered) / len(gold)
    recall_all = 1.0 if covered == gold else 0.0

    # Fact-level: how many individual retrieved facts come from gold sessions
    facts_from_gold = sum(1 for s in retrieved_session_ids if s in gold)
    fact_precision = facts_from_gold / facts_retrieved if facts_retrieved else 0.0

    return RetrievalMetrics(
        recall_all=recall_all,
        session_recall=session_recall,
        fact_precision=fact_precision,
        sessions_covered=len(covered),
        gold_sessions=len(gold),
        total_facts=total_facts,
        facts_retrieved=facts_retrieved,
        facts_from_gold=facts_from_gold,
        selectivity=facts_retrieved / total_facts if total_facts else 0,
    )
