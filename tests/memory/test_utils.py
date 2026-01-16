from datetime import UTC, datetime, timedelta, timezone

from ntrp.memory.utils import ensure_utc


class TestEnsureUtc:
    def test_none_returns_none(self):
        assert ensure_utc(None) is None

    def test_naive_datetime_gets_utc(self):
        naive = datetime(2024, 1, 1, 12, 0, 0)
        result = ensure_utc(naive)
        assert result.tzinfo == UTC

    def test_utc_datetime_unchanged(self):
        aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = ensure_utc(aware)
        assert result == aware

    def test_other_timezone_preserved(self):
        pst = timezone(offset=timedelta(hours=-8))
        aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=pst)
        result = ensure_utc(aware)
        assert result.tzinfo == pst
