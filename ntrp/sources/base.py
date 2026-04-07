from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from ntrp.sources.models import RawItem


@runtime_checkable
class Indexable(Protocol):
    name: str

    async def scan(self) -> list[RawItem]: ...


@dataclass(frozen=True)
class SourceItem:
    identity: str
    title: str
    source: str
    timestamp: datetime | None = None
    preview: str | None = None


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    published_date: str | None = None
    summary: str | None = None
    highlights: list[str] | None = None


@dataclass(frozen=True)
class WebContentResult:
    title: str | None
    url: str
    text: str | None = None
    published_date: str | None = None
    author: str | None = None


@runtime_checkable
class NotesSource(Protocol):
    name: str

    def read(self, source_id: str) -> str | None: ...

    def write(self, source_id: str, content: str) -> bool: ...

    def delete(self, source_id: str) -> bool: ...

    def exists(self, source_id: str) -> bool: ...

    def move(self, source_id: str, dest_id: str) -> bool: ...

    def search(self, query: str) -> list[str]: ...

    def scan(self) -> list[RawItem]: ...

    def scan_item(self, source_id: str) -> RawItem | None: ...

    def get_all_with_mtime(self) -> dict[str, datetime]: ...


@runtime_checkable
class EmailSource(Protocol):
    name: str

    def read(self, source_id: str) -> str | None: ...

    def search(self, query: str, limit: int) -> list[RawItem]: ...

    def list_recent(self, days: int, limit: int) -> list[SourceItem]: ...

    def list_accounts(self) -> list[str]: ...

    def send_email(self, account: str, to: str, subject: str, body: str) -> str: ...


@runtime_checkable
class CalendarSource(Protocol):
    name: str

    def search(self, query: str, limit: int) -> list[RawItem]: ...

    def get_upcoming(self, days: int, limit: int) -> list[RawItem]: ...

    def get_past(self, days: int, limit: int) -> list[RawItem]: ...

    def list_accounts(self) -> list[str]: ...

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

    def delete_event(self, event_id: str) -> str: ...

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


@runtime_checkable
class SlackSource(Protocol):
    name: str

    async def search_messages(self, query: str, limit: int = 20) -> list[RawItem]: ...

    async def search_channels(self, query: str | None = None, limit: int = 50) -> list[dict[str, str]]: ...

    async def search_users(self, query: str | None = None, limit: int = 50) -> list[dict[str, str]]: ...

    async def read_channel(self, channel: str, limit: int = 50) -> list[RawItem]: ...

    async def read_thread(self, source_id: str) -> str | None: ...

    async def read_user(self, user_id: str) -> dict | None: ...


@runtime_checkable
class WebSearchSource(Protocol):
    name: str

    def search_with_details(self, query: str, num_results: int, category: str | None) -> list[WebSearchResult]: ...

    def get_contents(self, urls: list[str]) -> list[WebContentResult]: ...
