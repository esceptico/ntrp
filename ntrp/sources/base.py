from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ntrp.sources.models import RawItem


class IndexableSource(Protocol):
    name: str

    async def scan(self) -> list[RawItem]: ...


class Source(ABC):
    name: str

    @property
    def errors(self) -> dict[str, str]:
        if not hasattr(self, "_errors"):
            self._errors: dict[str, str] = {}
        return self._errors

    @errors.setter
    def errors(self, value: dict[str, str]) -> None:
        self._errors = value

    @property
    def details(self) -> dict:
        return {}


@dataclass
class SourceItem:
    identity: str
    title: str
    source: str
    timestamp: datetime | None = None
    preview: str | None = None


@dataclass
class WebSearchResult:
    title: str
    url: str
    published_date: str | None = None
    summary: str | None = None
    highlights: list[str] | None = None


@dataclass
class WebContentResult:
    title: str | None
    url: str
    text: str | None = None
    published_date: str | None = None
    author: str | None = None


class NotesSource(Source):
    @abstractmethod
    def read(self, source_id: str) -> str | None: ...

    @abstractmethod
    def write(self, source_id: str, content: str) -> bool: ...

    @abstractmethod
    def delete(self, source_id: str) -> bool: ...

    @abstractmethod
    def exists(self, source_id: str) -> bool: ...

    @abstractmethod
    def move(self, source_id: str, dest_id: str) -> bool: ...

    @abstractmethod
    def search(self, query: str) -> list[str]: ...

    @abstractmethod
    def scan(self) -> list[RawItem]: ...

    @abstractmethod
    def scan_item(self, source_id: str) -> RawItem | None: ...

    @abstractmethod
    def get_all_with_mtime(self) -> dict[str, datetime]: ...


class EmailSource(Source):
    @abstractmethod
    def read(self, source_id: str) -> str | None: ...

    @abstractmethod
    def search(self, query: str, limit: int) -> list[RawItem]: ...

    @abstractmethod
    def list_recent(self, days: int, limit: int) -> list[SourceItem]: ...

    @abstractmethod
    def list_accounts(self) -> list[str]: ...

    @abstractmethod
    def send_email(self, account: str, to: str, subject: str, body: str) -> str: ...


class CalendarSource(Source):
    @abstractmethod
    def search(self, query: str, limit: int) -> list[RawItem]: ...

    @abstractmethod
    def get_upcoming(self, days: int, limit: int) -> list[RawItem]: ...

    @abstractmethod
    def get_past(self, days: int, limit: int) -> list[RawItem]: ...

    @abstractmethod
    def list_accounts(self) -> list[str]: ...

    @abstractmethod
    def create_event(
        self,
        account: str,
        summary: str,
        start: datetime,
        end: datetime | None,
        description: str,
        location: str,
        attendees: list[str] | None,
        all_day: bool,
    ) -> str: ...

    @abstractmethod
    def delete_event(self, event_id: str) -> str: ...

    @abstractmethod
    def update_event(
        self,
        event_id: str,
        summary: str | None,
        start: datetime | None,
        end: datetime | None,
        description: str | None,
        location: str | None,
        attendees: list[str] | None,
        all_day: bool | None,
    ) -> str: ...


class BrowserSource(Source):
    @abstractmethod
    def read(self, source_id: str) -> str | None: ...

    @abstractmethod
    def search(self, query: str) -> list[str]: ...

    @abstractmethod
    def list_recent(self, days: int, limit: int) -> list[SourceItem]: ...


class WebSearchSource(Source):
    @abstractmethod
    def search_with_details(self, query: str, num_results: int, category: str | None) -> list[WebSearchResult]: ...

    @abstractmethod
    def get_contents(self, urls: list[str]) -> list[WebContentResult]: ...
