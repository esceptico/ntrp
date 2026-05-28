import json
from types import SimpleNamespace

import pytest

from ntrp.benchmarks.longmemeval import LongMemEvalRunnerConfig, load_longmemeval_cases, run_longmemeval


@pytest.mark.asyncio
async def test_longmemeval_runner_writes_metrics_and_traces(tmp_path):
    dataset = tmp_path / "longmemeval-mini.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "case_degree",
                    "question_type": "single-session-user",
                    "question": "What degree did I graduate with?",
                    "answer": "Business Administration",
                    "answer_session_ids": ["answer_degree"],
                    "haystack_dates": ["2023/05/20 (Sat) 02:21", "2023/05/20 (Sat) 03:00"],
                    "haystack_session_ids": ["distractor_degree", "answer_degree"],
                    "haystack_sessions": [
                        [{"role": "user", "content": "I have been cooking pasta and learning guitar."}],
                        [
                            {
                                "role": "user",
                                "content": "I graduated with a degree in Business Administration before moving cities.",
                            }
                        ],
                    ],
                },
                {
                    "question_id": "case_preference",
                    "question_type": "single-session-preference",
                    "question": "What tea do I prefer in the evening?",
                    "answer": "jasmine tea",
                    "answer_session_ids": ["answer_tea"],
                    "haystack_dates": ["2023/05/21 (Sun) 19:00"],
                    "haystack_session_ids": ["answer_tea"],
                    "haystack_sessions": [
                        [{"role": "user", "content": "In the evening I prefer jasmine tea over coffee."}]
                    ],
                },
            ]
        ),
        encoding="utf-8",
    )

    result = await run_longmemeval(
        LongMemEvalRunnerConfig(
            dataset_path=dataset,
            output_dir=tmp_path / "results",
            top_k=5,
            budget_chars=5_000,
            run_id="test-run",
        )
    )

    metrics = result["metrics"]
    assert metrics["cases"] == 2
    assert metrics["variant"] == "raw-episodes"
    assert metrics["recall_at_k"] == 1.0
    assert metrics["mrr_at_k"] > 0
    assert set(metrics["by_question_type"]) == {"single-session-preference", "single-session-user"}

    traces_path = tmp_path / "results" / "longmemeval-test-run" / "traces.jsonl"
    failures_path = tmp_path / "results" / "longmemeval-test-run" / "failures.jsonl"
    metrics_path = tmp_path / "results" / "longmemeval-test-run" / "metrics.json"
    assert traces_path.exists()
    assert failures_path.exists()
    assert metrics_path.exists()
    traces = [json.loads(line) for line in traces_path.read_text(encoding="utf-8").splitlines()]
    assert len(traces) == 2
    assert traces[0]["candidates"][0]["source_ids"]
    assert json.loads(metrics_path.read_text(encoding="utf-8"))["run_id"] == "test-run"



@pytest.mark.asyncio
async def test_longmemeval_semantic_alias_retrieves_named_streaming_service(tmp_path):
    dataset = tmp_path / "longmemeval-semantic-alias-mini.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "case_spotify",
                    "question_type": "single-session-user",
                    "question": "What is the name of the music streaming service I have been using lately?",
                    "answer": "Spotify",
                    "answer_session_ids": ["answer_spotify"],
                    "haystack_dates": ["2023/05/20 (Sat) 10:20", "2023/05/20 (Sat) 11:00"],
                    "haystack_session_ids": ["distractor_music", "answer_spotify"],
                    "haystack_sessions": [
                        [{"role": "user", "content": "I need general music recommendations for live concerts."}],
                        [
                            {
                                "role": "user",
                                "content": "I've been listening to Arctic Monkeys and The Neighbourhood a lot on Spotify lately.",
                            }
                        ],
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = await run_longmemeval(
        LongMemEvalRunnerConfig(
            dataset_path=dataset,
            output_dir=tmp_path / "results",
            top_k=1,
            budget_chars=5_000,
            run_id="semantic-alias-test-run",
            raw_evidence_query=False,
            variant="raw-episodes",
        )
    )

    assert result["metrics"]["recall_at_k"] == 1.0
    traces_path = tmp_path / "results" / "longmemeval-semantic-alias-test-run" / "traces.jsonl"
    trace = json.loads(traces_path.read_text(encoding="utf-8"))
    assert trace["candidates"][0]["source_ids"][0] == "answer_spotify"
    assert {"semantic_alias_match", "claim_match", "vector_match"} & set(trace["candidates"][0]["reasons"])


def test_longmemeval_loader_accepts_samples_shape(tmp_path):
    dataset = tmp_path / "longmemeval-samples-shape.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "type": "temporal-reasoning",
                    "question": "Which event happened first?",
                    "answer": "The lens arrived",
                    "sessions": [[{"role": "user", "content": "The lens arrived before the road trip."}]],
                }
            ]
        ),
        encoding="utf-8",
    )

    cases = load_longmemeval_cases(dataset)

    assert cases[0]["question_type"] == "temporal-reasoning"
    assert cases[0]["answer_session_ids"] == ["case_00000_session_0"]

@pytest.mark.asyncio
async def test_longmemeval_extracted_variant_uses_turn_fact_candidates(tmp_path):
    dataset = tmp_path / "longmemeval-mini.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "case_degree",
                    "question_type": "single-session-user",
                    "question": "What degree did I graduate with?",
                    "answer": "Business Administration",
                    "answer_session_ids": ["answer_degree"],
                    "haystack_dates": ["2023/05/20 (Sat) 02:21"],
                    "haystack_session_ids": ["answer_degree"],
                    "haystack_sessions": [
                        [
                            {
                                "role": "user",
                                "content": "I graduated with a degree in Business Administration before moving cities.",
                            }
                        ]
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = await run_longmemeval(
        LongMemEvalRunnerConfig(
            dataset_path=dataset,
            output_dir=tmp_path / "results",
            top_k=5,
            budget_chars=5_000,
            run_id="extracted-test-run",
            raw_evidence_query=False,
            variant="extracted",
        )
    )

    metrics = result["metrics"]
    assert metrics["variant"] == "extracted"
    assert metrics["recall_at_k"] == 1.0
    traces_path = tmp_path / "results" / "longmemeval-extracted-test-run" / "traces.jsonl"
    trace = json.loads(traces_path.read_text(encoding="utf-8").splitlines()[0])
    assert any(candidate["object_type"] == "fact" for candidate in trace["candidates"])
    assert not any(candidate["object_type"] == "memory_episode" for candidate in trace["candidates"])


@pytest.mark.asyncio
async def test_longmemeval_extracted_variant_can_use_model_episode_extraction(tmp_path, monkeypatch):
    dataset = tmp_path / "longmemeval-model-extracted-mini.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "case_model_extract",
                    "question_type": "single-session-user",
                    "question": "What breed is my dog?",
                    "answer": "Golden Retriever",
                    "answer_session_ids": ["answer_dog"],
                    "haystack_dates": ["2023/05/21 (Sun) 19:00"],
                    "haystack_session_ids": ["answer_dog"],
                    "haystack_sessions": [[{"role": "user", "content": "Max is a Golden Retriever and needs a new collar."}]],
                }
            ]
        ),
        encoding="utf-8",
    )

    class _FakeClient:
        async def completion(self, **kwargs):
            content = json.dumps(
                {
                    "memories": [
                        {
                            "object_type": "fact",
                            "title": "Max is a Golden Retriever",
                            "text": "The user's dog Max is a Golden Retriever.",
                            "kind": "pet_fact",
                            "confidence": 0.95,
                            "source_quote": "Max is a Golden Retriever",
                        }
                    ]
                }
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    import ntrp.llm.router as router

    monkeypatch.setattr(router, "get_completion_client", lambda model: _FakeClient())

    result = await run_longmemeval(
        LongMemEvalRunnerConfig(
            dataset_path=dataset,
            output_dir=tmp_path / "results",
            top_k=5,
            budget_chars=5_000,
            run_id="model-extracted-test-run",
            raw_evidence_query=False,
            variant="extracted",
            extraction_model="test-extraction-model",
            evaluate_answers=True,
        )
    )

    assert result["metrics"]["extraction_model"] == "test-extraction-model"
    assert result["metrics"]["answer_eval"]["answer_accuracy"] == 1.0
    traces_path = tmp_path / "results" / "longmemeval-model-extracted-test-run" / "traces.jsonl"
    trace = json.loads(traces_path.read_text(encoding="utf-8"))
    assert any(candidate["object_type"] == "fact" for candidate in trace["candidates"])
    assert not any(candidate["object_type"] == "memory_episode" for candidate in trace["candidates"])


@pytest.mark.asyncio
async def test_longmemeval_raw_plus_extracted_variant_includes_both_candidate_types(tmp_path):
    dataset = tmp_path / "longmemeval-mini.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "case_degree_combo",
                    "question_type": "single-session-user",
                    "question": "What degree did I graduate with?",
                    "answer": "Business Administration",
                    "answer_session_ids": ["answer_degree"],
                    "haystack_dates": ["2023/05/20 (Sat) 02:21"],
                    "haystack_session_ids": ["answer_degree"],
                    "haystack_sessions": [
                        [
                            {
                                "role": "user",
                                "content": "I graduated with a degree in Business Administration before moving cities.",
                            }
                        ]
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = await run_longmemeval(
        LongMemEvalRunnerConfig(
            dataset_path=dataset,
            output_dir=tmp_path / "results",
            top_k=5,
            budget_chars=5_000,
            run_id="raw-plus-extracted-test-run",
            raw_evidence_query=False,
            variant="raw-plus-extracted",
        )
    )

    assert result["metrics"]["variant"] == "raw-plus-extracted"
    assert result["metrics"]["variant_components"] == {"raw_episodes": True, "extracted_facts": True}
    traces_path = tmp_path / "results" / "longmemeval-raw-plus-extracted-test-run" / "traces.jsonl"
    trace = json.loads(traces_path.read_text(encoding="utf-8").splitlines()[0])
    assert trace["candidates"]



@pytest.mark.asyncio
async def test_longmemeval_answer_eval_scores_correct_cited_answer(tmp_path):
    dataset = tmp_path / "longmemeval-answer-mini.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "case_evening_tea",
                    "question_type": "single-session-preference",
                    "question": "What tea do I prefer in the evening?",
                    "answer": "jasmine tea",
                    "answer_session_ids": ["answer_tea"],
                    "haystack_dates": ["2023/05/21 (Sun) 19:00"],
                    "haystack_session_ids": ["answer_tea"],
                    "haystack_sessions": [
                        [{"role": "user", "content": "In the evening I prefer jasmine tea over coffee."}]
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = await run_longmemeval(
        LongMemEvalRunnerConfig(
            dataset_path=dataset,
            output_dir=tmp_path / "results",
            top_k=5,
            budget_chars=5_000,
            run_id="answer-eval-test-run",
            raw_evidence_query=False,
            evaluate_answers=True,
        )
    )

    metrics = result["metrics"]
    assert metrics["answer_eval"]["answer_accuracy"] == 1.0
    assert metrics["answer_eval"]["source_grounding_rate"] == 1.0
    assert metrics["answer_eval"]["grounded_correct_rate"] == 1.0
    trace_path = tmp_path / "results" / "longmemeval-answer-eval-test-run" / "traces.jsonl"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["answer_eval"]["correct"] is True
    assert trace["answer_eval"]["cited_gold_source"] is True
    assert trace["answer_generation"]["cited_source_ids"] == ["answer_tea"]


@pytest.mark.asyncio
async def test_longmemeval_answer_eval_flags_right_source_wrong_answer(tmp_path):
    dataset = tmp_path / "longmemeval-answer-failure-mini.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "case_degree_wrong_expected",
                    "question_type": "single-session-user",
                    "question": "What degree did I graduate with?",
                    "answer": "Physics",
                    "answer_session_ids": ["answer_degree"],
                    "haystack_dates": ["2023/05/20 (Sat) 03:00"],
                    "haystack_session_ids": ["answer_degree"],
                    "haystack_sessions": [
                        [
                            {
                                "role": "user",
                                "content": "I graduated with a degree in Business Administration before moving cities.",
                            }
                        ]
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = await run_longmemeval(
        LongMemEvalRunnerConfig(
            dataset_path=dataset,
            output_dir=tmp_path / "results",
            top_k=5,
            budget_chars=5_000,
            run_id="answer-failure-test-run",
            raw_evidence_query=False,
            evaluate_answers=True,
        )
    )

    metrics = result["metrics"]
    assert metrics["recall_at_k"] == 1.0
    assert metrics["answer_eval"]["answer_accuracy"] == 0.0
    assert metrics["answer_eval"]["failure_classes"] == {"right_source_wrong_answer": 1}
    failures_path = tmp_path / "results" / "longmemeval-answer-failure-test-run" / "failures.jsonl"
    failure = json.loads(failures_path.read_text(encoding="utf-8"))
    assert failure["failure_class"] == "right_source_wrong_answer"
    assert failure["retrieval_failure_class"] is None


@pytest.mark.asyncio
async def test_longmemeval_answer_eval_flags_partial_gold_context(tmp_path):
    dataset = tmp_path / "longmemeval-partial-gold-mini.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "case_partial_gold",
                    "question_type": "temporal-reasoning",
                    "question": "Which seeds were started first, tomatoes or marigolds?",
                    "answer": "tomatoes and marigolds",
                    "answer_session_ids": ["answer_tomatoes", "answer_marigolds"],
                    "haystack_dates": ["2023/03/01", "2023/03/03"],
                    "haystack_session_ids": ["answer_tomatoes", "answer_marigolds"],
                    "haystack_sessions": [
                        [{"role": "user", "content": "I started the tomatoes in seed trays on March 1."}],
                        [{"role": "user", "content": "I started the marigolds in seed trays on March 3."}],
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = await run_longmemeval(
        LongMemEvalRunnerConfig(
            dataset_path=dataset,
            output_dir=tmp_path / "results",
            top_k=1,
            budget_chars=5_000,
            run_id="partial-gold-test-run",
            raw_evidence_query=False,
            evaluate_answers=True,
        )
    )

    metrics = result["metrics"]
    assert metrics["recall_at_k"] == 1.0
    assert metrics["gold_session_coverage_at_k"] == 0.5
    assert metrics["all_gold_retrieved_rate"] == 0.0
    assert metrics["answer_eval"]["failure_classes"] == {"partial_gold_context_wrong_answer": 1}
    trace_path = tmp_path / "results" / "longmemeval-partial-gold-test-run" / "traces.jsonl"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["all_gold_retrieved"] is False
    assert trace["reliability_warnings"] == ["partial_gold_retrieved"]


@pytest.mark.asyncio
async def test_longmemeval_answer_eval_composes_day_delta_answer(tmp_path):
    dataset = tmp_path / "longmemeval-day-delta-mini.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "case_day_delta",
                    "question_type": "temporal-reasoning",
                    "question": "How many days before the team meeting did I attend the workshop?",
                    "answer": "7 days. 8 days (including the last day) is also acceptable.",
                    "answer_session_ids": ["answer_workshop", "answer_meeting"],
                    "haystack_dates": ["2023/01/13", "2023/01/13"],
                    "haystack_session_ids": ["answer_workshop", "answer_meeting"],
                    "haystack_sessions": [
                        [{"role": "user", "content": "I attended the workshop on January 10th."}],
                        [{"role": "user", "content": "The team meeting is scheduled for January 17th."}],
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = await run_longmemeval(
        LongMemEvalRunnerConfig(
            dataset_path=dataset,
            output_dir=tmp_path / "results",
            top_k=5,
            budget_chars=5_000,
            run_id="day-delta-test-run",
            raw_evidence_query=False,
            evaluate_answers=True,
        )
    )

    metrics = result["metrics"]
    assert metrics["answer_eval"]["answer_accuracy"] == 1.0
    trace_path = tmp_path / "results" / "longmemeval-day-delta-test-run" / "traces.jsonl"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["answer_generation"]["generated_answer"].startswith("7 days.")


@pytest.mark.asyncio
async def test_longmemeval_answer_eval_composes_money_total_answer(tmp_path):
    dataset = tmp_path / "longmemeval-money-total-mini.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "case_money_total",
                    "question_type": "multi-session",
                    "question": "How much total money have I spent on bike-related expenses?",
                    "answer": "$185",
                    "answer_session_ids": ["answer_helmet", "answer_chain", "answer_lights"],
                    "haystack_dates": ["2023/05/01", "2023/05/02", "2023/05/03"],
                    "haystack_session_ids": ["answer_helmet", "answer_chain", "answer_lights"],
                    "haystack_sessions": [
                        [{"role": "user", "content": "I bought a Bell Zephyr bike helmet for $120."}],
                        [{"role": "user", "content": "The bike chain replacement cost me $25."}],
                        [{"role": "user", "content": "I bought bike lights for $40."}],
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = await run_longmemeval(
        LongMemEvalRunnerConfig(
            dataset_path=dataset,
            output_dir=tmp_path / "results",
            top_k=5,
            budget_chars=5_000,
            run_id="money-total-test-run",
            raw_evidence_query=False,
            evaluate_answers=True,
        )
    )

    metrics = result["metrics"]
    assert metrics["answer_eval"]["answer_accuracy"] == 1.0
    trace_path = tmp_path / "results" / "longmemeval-money-total-test-run" / "traces.jsonl"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["answer_generation"]["generated_answer"].startswith("$185.")


@pytest.mark.asyncio
async def test_longmemeval_answer_eval_can_use_mocked_llm_answer_and_judge(tmp_path, monkeypatch):
    dataset = tmp_path / "longmemeval-llm-answer-mini.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "case_llm_breed",
                    "question_type": "single-session-user",
                    "question": "What breed is my dog?",
                    "answer": "Golden Retriever",
                    "answer_session_ids": ["answer_dog"],
                    "haystack_dates": ["2023/05/21 (Sun) 19:00"],
                    "haystack_session_ids": ["answer_dog"],
                    "haystack_sessions": [
                        [{"role": "user", "content": "Max is a Golden Retriever and needs a new collar."}]
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    class _FakeClient:
        async def completion(self, **kwargs):
            schema_name = kwargs["response_format"].__name__
            if schema_name == "_LLMAnswer":
                content = json.dumps({"answer": "Max is a Golden Retriever.", "cited_source_ids": ["answer_dog"]})
            else:
                content = json.dumps({"correct": True, "source_grounded": True, "reason": "Matches cited source."})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    import ntrp.llm.router as router

    monkeypatch.setattr(router, "get_completion_client", lambda model: _FakeClient())

    result = await run_longmemeval(
        LongMemEvalRunnerConfig(
            dataset_path=dataset,
            output_dir=tmp_path / "results",
            top_k=5,
            budget_chars=5_000,
            run_id="llm-answer-test-run",
            raw_evidence_query=False,
            evaluate_answers=True,
            answer_model="test-answer-model",
            judge_model="test-judge-model",
        )
    )

    answer_eval = result["metrics"]["answer_eval"]
    assert answer_eval["answer_model"] == "test-answer-model"
    assert answer_eval["judge_model"] == "test-judge-model"
    assert answer_eval["answer_accuracy"] == 1.0
    assert answer_eval["grounded_correct_rate"] == 1.0
