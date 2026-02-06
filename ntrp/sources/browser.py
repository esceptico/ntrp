import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from ntrp.config import get_config
from ntrp.sources.base import BrowserSource, SourceItem
from ntrp.sources.models import RawItem

# Browser history DB locations (macOS)
BROWSER_PATHS = {
    "chrome": Path.home() / "Library/Application Support/Google/Chrome/Default/History",
    "safari": Path.home() / "Library/Safari/History.db",
    "arc": Path.home() / "Library/Application Support/Arc/User Data/Default/History",
}


class BrowserHistorySource(BrowserSource):
    name = "browser"

    def __init__(self):
        config = get_config()
        if not config.browser:
            raise ValueError("Browser not configured")
        self.browser = config.browser
        self.days_back = config.browser_days
        self.db_path = BROWSER_PATHS.get(self.browser)

        if not self.db_path or not self.db_path.exists():
            raise ValueError(f"Browser history not found: {self.browser} at {self.db_path}")

    @property
    def details(self) -> dict:
        return {"type": self.browser, "days": self.days_back}

    def _copy_db(self) -> Path:
        fd, temp_path_str = tempfile.mkstemp(suffix=".db")
        os.close(fd)  # Close the file descriptor, we just need the path
        temp_path = Path(temp_path_str)
        shutil.copy2(self.db_path, temp_path)
        return temp_path

    @contextmanager
    def _open_db(self):
        temp_db = self._copy_db()
        try:
            conn = sqlite3.connect(temp_db)
            try:
                yield conn
            finally:
                conn.close()
        finally:
            if temp_db.exists():
                temp_db.unlink()

    def _chrome_epoch_to_datetime(self, chrome_time: int) -> datetime:
        # Chrome uses microseconds since Jan 1, 1601
        return datetime(1601, 1, 1) + timedelta(microseconds=chrome_time)

    def _safari_epoch_to_datetime(self, safari_time: float) -> datetime:
        # Safari uses seconds since Jan 1, 2001
        return datetime(2001, 1, 1) + timedelta(seconds=safari_time)

    def scan(self, limit: int = 500, days_back: int | None = None) -> list[RawItem]:
        days = days_back if days_back is not None else self.days_back

        with self._open_db() as conn:
            cursor = conn.cursor()

            if self.browser in ("chrome", "arc"):
                # Chrome/Arc schema
                cutoff = datetime.now() - timedelta(days=days)
                # Chrome time is microseconds since 1601
                chrome_cutoff = int((cutoff - datetime(1601, 1, 1)).total_seconds() * 1_000_000)

                cursor.execute(
                    """
                    SELECT url, title, visit_count, last_visit_time
                    FROM urls
                    WHERE last_visit_time > ?
                    ORDER BY last_visit_time DESC
                    LIMIT ?
                """,
                    (chrome_cutoff, limit),
                )

                items = []
                for url, title, visit_count, last_visit_time in cursor:
                    if not title or not url:
                        continue
                    # Skip internal/extension URLs
                    if url.startswith(("chrome://", "chrome-extension://", "about:")):
                        continue

                    visited_at = self._chrome_epoch_to_datetime(last_visit_time)

                    items.append(
                        RawItem(
                            source="browser",
                            source_id=url,
                            title=title or url,
                            content=f"URL: {url}\nTitle: {title}\nVisits: {visit_count}\nLast visited: {visited_at.isoformat()}",
                            created_at=visited_at,
                            updated_at=visited_at,
                            metadata={
                                "browser": self.browser,
                                "url": url,
                                "visit_count": visit_count,
                            },
                        )
                    )

                return items

            elif self.browser == "safari":
                # Safari schema
                cutoff = datetime.now() - timedelta(days=days)
                safari_cutoff = (cutoff - datetime(2001, 1, 1)).total_seconds()

                cursor.execute(
                    """
                    SELECT
                        history_items.url,
                        history_visits.title,
                        history_visits.visit_time
                    FROM history_visits
                    JOIN history_items ON history_visits.history_item = history_items.id
                    WHERE history_visits.visit_time > ?
                    ORDER BY history_visits.visit_time DESC
                    LIMIT ?
                """,
                    (safari_cutoff, limit),
                )

                items = []
                for url, title, visit_time in cursor:
                    if not url:
                        continue

                    visited_at = self._safari_epoch_to_datetime(visit_time)

                    items.append(
                        RawItem(
                            source="browser",
                            source_id=url,
                            title=title or url,
                            content=f"URL: {url}\nTitle: {title}\nLast visited: {visited_at.isoformat()}",
                            created_at=visited_at,
                            updated_at=visited_at,
                            metadata={
                                "browser": self.browser,
                                "url": url,
                            },
                        )
                    )

                return items

            return []

    def read(self, source_id: str) -> str | None:
        with self._open_db() as conn:
            cursor = conn.cursor()

            if self.browser in ("chrome", "arc"):
                cursor.execute("SELECT url, title, visit_count, last_visit_time FROM urls WHERE url = ?", (source_id,))
                row = cursor.fetchone()
                if row:
                    url, title, visit_count, last_visit_time = row
                    visited_at = self._chrome_epoch_to_datetime(last_visit_time)
                    return f"URL: {url}\nTitle: {title}\nVisit count: {visit_count}\nLast visited: {visited_at}"

            elif self.browser == "safari":
                cursor.execute(
                    """
                    SELECT history_items.url, history_visits.title, history_visits.visit_time
                    FROM history_visits
                    JOIN history_items ON history_visits.history_item = history_items.id
                    WHERE history_items.url = ?
                    ORDER BY history_visits.visit_time DESC
                    LIMIT 1
                """,
                    (source_id,),
                )
                row = cursor.fetchone()
                if row:
                    url, title, visit_time = row
                    visited_at = self._safari_epoch_to_datetime(visit_time)
                    return f"URL: {url}\nTitle: {title or 'No title'}\nLast visited: {visited_at}"

            return None

    def search(self, pattern: str) -> list[str]:
        with self._open_db() as conn:
            cursor = conn.cursor()

            if self.browser in ("chrome", "arc"):
                cursor.execute(
                    "SELECT url FROM urls WHERE url LIKE ? OR title LIKE ? LIMIT 50", (f"%{pattern}%", f"%{pattern}%")
                )
                return [row[0] for row in cursor]

            elif self.browser == "safari":
                cursor.execute(
                    """
                    SELECT DISTINCT history_items.url
                    FROM history_visits
                    JOIN history_items ON history_visits.history_item = history_items.id
                    WHERE history_items.url LIKE ? OR history_visits.title LIKE ?
                    ORDER BY history_visits.visit_time DESC
                    LIMIT 50
                """,
                    (f"%{pattern}%", f"%{pattern}%"),
                )
                return [row[0] for row in cursor]

            return []

    def list_recent(self, days: int = 7, limit: int = 50) -> list[SourceItem]:
        raw_items = self.scan(limit=limit, days_back=days)
        return [
            SourceItem(
                identity=item.source_id,
                title=item.title,
                source=self.name,
                timestamp=item.created_at,
                preview=item.metadata.get("url"),
            )
            for item in raw_items
        ]
