from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ntrp.sources.base import CalendarSource
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

SEARCH_CALENDAR_DESCRIPTION = """Search calendar events by text query.

Use this to find specific events by name, attendee, or description."""

CREATE_CALENDAR_EVENT_DESCRIPTION = """Create a new calendar event.

Use this to schedule meetings, reminders, or block time on the calendar.
Requires user approval before creating."""

EDIT_CALENDAR_EVENT_DESCRIPTION = """Edit an existing calendar event.

Use list_calendar or search_calendar first to find the event ID.
Only provide the fields you want to change - others remain unchanged.
Requires user approval before editing."""

DELETE_CALENDAR_EVENT_DESCRIPTION = """Delete a calendar event by ID.

Use list_calendar or search_calendar first to find the event ID.
Requires user approval before deleting."""

LIST_CALENDAR_DESCRIPTION = """List calendar events.

Use days_forward for upcoming events, days_back for past events.
Use search_calendar to find specific events by name."""


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


class SearchCalendarInput(BaseModel):
    query: str = Field(description="Search query (searches title, description, attendees)")
    limit: int = Field(default=10, description="Max results (default: 10)")


class SearchCalendarTool(Tool):
    name = "search_calendar"
    description = SEARCH_CALENDAR_DESCRIPTION
    source_type = CalendarSource
    input_model = SearchCalendarInput

    def __init__(self, source: CalendarSource):
        self.source = source

    async def execute(self, execution: ToolExecution, query: str = "", limit: int = 10, **kwargs: Any) -> ToolResult:
        if not query:
            return ToolResult("Error: query is required", "Missing query")

        try:
            events = self.source.search(query, limit=limit)

            if not events:
                return ToolResult(
                    f"No events found matching '{query}'. Try different keywords or use list_calendar for upcoming.",
                    "0 events",
                )

            lines = [f"**Events matching '{query}':**\n"]
            for event in events:
                meta = event.metadata
                start = meta.get("start", "")
                event_id = event.source_id

                if start:
                    dt = datetime.fromisoformat(start)
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    time_str = "No time"

                lines.append(f"- **{time_str}**: {event.title} `[{event_id}]`")

            return ToolResult("\n".join(lines), f"{len(events)} events")
        except Exception as e:
            return ToolResult(f"Error searching events: {e}", "Search failed")


class CreateCalendarEventInput(BaseModel):
    summary: str = Field(description="Event title/summary")
    start: str = Field(description="Start time in ISO format (e.g., '2024-01-15T14:00:00')")
    end: str | None = Field(default=None, description="End time in ISO format (optional, defaults to 1 hour after start)")
    description: str | None = Field(default=None, description="Event description (optional)")
    location: str | None = Field(default=None, description="Event location (optional)")
    attendees: str | None = Field(default=None, description="Comma-separated email addresses of attendees (optional)")
    all_day: bool = Field(default=False, description="Whether this is an all-day event (optional)")
    account: str | None = Field(default=None, description="Calendar account email (optional if only one account)")


class CreateCalendarEventTool(Tool):
    name = "create_calendar_event"
    description = CREATE_CALENDAR_EVENT_DESCRIPTION
    mutates = True
    source_type = CalendarSource
    input_model = CreateCalendarEventInput

    def __init__(self, source: CalendarSource):
        self.source = source

    async def execute(
        self,
        execution: ToolExecution,
        summary: str = "",
        start: str = "",
        end: str = "",
        description: str = "",
        location: str = "",
        attendees: str = "",
        all_day: bool = False,
        account: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        if not summary:
            return ToolResult("Error: summary is required", "Missing summary")
        if not start:
            return ToolResult("Error: start time is required", "Missing start")

        start_dt = _parse_datetime(start)
        if not start_dt:
            return ToolResult(f"Invalid start time: {start}. Use ISO format: 2024-01-15T14:00:00", "Invalid start")

        end_dt = _parse_datetime(end)
        attendee_list = [e.strip() for e in attendees.split(",") if e.strip()] if attendees else None

        time_str = start_dt.strftime("%Y-%m-%d %H:%M")
        if end_dt:
            time_str += f" - {end_dt.strftime('%H:%M')}"

        await execution.require_approval(summary, preview=f"Time: {time_str}\nLocation: {location or 'N/A'}")

        result = self.source.create_event(
            account=account,
            summary=summary,
            start=start_dt,
            end=end_dt,
            description=description,
            location=location,
            attendees=attendee_list,
            all_day=all_day,
        )
        return ToolResult(result, "Created")


class EditCalendarEventInput(BaseModel):
    event_id: str = Field(description="The event ID to edit (from list_calendar or search_calendar)")
    summary: str | None = Field(default=None, description="New event title (optional)")
    start: str | None = Field(default=None, description="New start time in ISO format (optional)")
    end: str | None = Field(default=None, description="New end time in ISO format (optional)")
    description: str | None = Field(default=None, description="New event description (optional)")
    location: str | None = Field(default=None, description="New event location (optional)")
    attendees: str | None = Field(default=None, description="New comma-separated attendee emails (optional, replaces existing)")


class EditCalendarEventTool(Tool):
    name = "edit_calendar_event"
    description = EDIT_CALENDAR_EVENT_DESCRIPTION
    mutates = True
    source_type = CalendarSource
    input_model = EditCalendarEventInput

    def __init__(self, source: CalendarSource):
        self.source = source

    async def execute(
        self,
        execution: ToolExecution,
        event_id: str = "",
        summary: str = "",
        start: str = "",
        end: str = "",
        description: str = "",
        location: str = "",
        attendees: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        if not event_id:
            return ToolResult("Error: event_id is required", "Missing event_id")

        start_dt = _parse_datetime(start)
        if start and not start_dt:
            return ToolResult(f"Invalid start time: {start}. Use ISO format: 2024-01-15T14:00:00", "Invalid start")

        end_dt = _parse_datetime(end)
        if end and not end_dt:
            return ToolResult(f"Invalid end time: {end}. Use ISO format: 2024-01-15T15:00:00", "Invalid end")

        attendee_list = [e.strip() for e in attendees.split(",") if e.strip()] if attendees else None

        changes = []
        if summary:
            changes.append(f"Title: {summary}")
        if start:
            changes.append(f"Start: {start}")
        if end:
            changes.append(f"End: {end}")
        if location:
            changes.append(f"Location: {location}")

        await execution.require_approval(event_id, preview="\n".join(changes) if changes else "No changes")

        result = self.source.update_event(
            event_id=event_id,
            summary=summary if summary else None,
            start=start_dt,
            end=end_dt,
            description=description if description else None,
            location=location if location else None,
            attendees=attendee_list,
        )
        return ToolResult(result, "Updated")


class DeleteCalendarEventInput(BaseModel):
    event_id: str = Field(description="The event ID to delete")


class DeleteCalendarEventTool(Tool):
    name = "delete_calendar_event"
    description = DELETE_CALENDAR_EVENT_DESCRIPTION
    mutates = True
    source_type = CalendarSource
    input_model = DeleteCalendarEventInput

    def __init__(self, source: CalendarSource):
        self.source = source

    async def execute(self, execution: ToolExecution, event_id: str = "", **kwargs: Any) -> ToolResult:
        if not event_id:
            return ToolResult("Error: event_id is required", "Missing event_id")

        await execution.require_approval(event_id)

        result = self.source.delete_event(event_id)
        return ToolResult(result, "Deleted")


class ListCalendarInput(BaseModel):
    days_forward: int = Field(default=7, description="Days ahead to look (default: 7)")
    days_back: int = Field(default=0, description="Days back to look (default: 0)")
    limit: int = Field(default=30, description="Maximum results (default: 30)")


class ListCalendarTool(Tool):
    name = "list_calendar"
    description = LIST_CALENDAR_DESCRIPTION
    source_type = CalendarSource
    input_model = ListCalendarInput

    def __init__(self, source: CalendarSource):
        self.source = source

    async def execute(
        self,
        execution: ToolExecution,
        days_forward: int = 7,
        days_back: int = 0,
        limit: int = 30,
        **kwargs: Any,
    ) -> ToolResult:
        events = []

        if days_back > 0:
            past = self.source.get_past(days=days_back, limit=limit)
            events.extend(past)

        if days_forward > 0:
            upcoming = self.source.get_upcoming(days=days_forward, limit=limit)
            events.extend(upcoming)

        if not events:
            return ToolResult("No calendar events in the specified range", "0 events")

        events.sort(key=lambda e: e.metadata.get("start", ""))

        output = []
        for event in events[:limit]:
            meta = event.metadata
            start = meta.get("start", "")

            if start:
                dt = datetime.fromisoformat(start)
                if meta.get("is_all_day"):
                    time_str = dt.strftime("%a %b %d") + " (all day)"
                else:
                    time_str = dt.strftime("%a %b %d, %H:%M")
            else:
                time_str = "No time"

            location = f" @ {meta['location']}" if meta.get("location") else ""
            output.append(f"• {time_str}: {event.title}{location}")

        return ToolResult("\n".join(output), f"{len(events)} events")
