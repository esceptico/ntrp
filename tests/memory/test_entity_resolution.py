from datetime import datetime, timedelta

from ntrp.memory.entity_resolution import (
    compute_resolution_score,
    name_similarity,
    temporal_proximity_score,
)


class TestNameSimilarity:
    def test_exact_match(self):
        assert name_similarity("Alice", "Alice") == 1.0
        assert name_similarity("alice", "ALICE") == 1.0

    def test_prefix_match(self):
        score = name_similarity("Alex", "Alexander")
        assert 0.7 < score < 1.0

    def test_no_match(self):
        score = name_similarity("Alice", "Bob")
        assert score < 0.5


class TestTemporalProximityScore:
    def test_none_returns_neutral(self):
        score = temporal_proximity_score(None, datetime.now())
        assert score == 0.5

    def test_same_time_is_high(self):
        now = datetime.now()
        score = temporal_proximity_score(now, now)
        assert score > 0.99

    def test_old_time_decays(self):
        now = datetime.now()
        old = now - timedelta(days=30)
        score = temporal_proximity_score(now, old)
        assert score < 0.5


class TestComputeResolutionScore:
    def test_high_cooccurrence_dominates(self):
        score = compute_resolution_score(
            name_sim=0.5,
            co_occurrence=1.0,
            temporal=0.5,
        )
        assert score > 0.8

    def test_zero_cooccurrence_low_name_sim(self):
        score = compute_resolution_score(
            name_sim=0.3,
            co_occurrence=0.0,
            temporal=0.5,
        )
        assert score < 0.2

    def test_mixed_signals(self):
        score = compute_resolution_score(
            name_sim=0.7,
            co_occurrence=0.5,
            temporal=0.8,
        )
        assert 0.4 < score < 0.7
