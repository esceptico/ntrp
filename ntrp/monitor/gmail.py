import asyncio
import json
from collections.abc import Coroutine
from typing import Any

from google.cloud import pubsub_v1
from googleapiclient.errors import HttpError

from ntrp.channel import Channel
from ntrp.constants import GMAIL_PUBSUB_SUBSCRIPTION, GMAIL_PUBSUB_TOPIC
from ntrp.events.triggers import NewEmail
from ntrp.logging import get_logger
from ntrp.monitor.store import MonitorStateStore
from ntrp.sources.google.gmail import (
    GmailSource,
    decode_email_header,
    extract_headers,
    parse_email_date,
)

_logger = get_logger(__name__)

WATCH_RENEWAL_INTERVAL = 6 * 3600  # re-register watches every 6 hours (expire after 7 days)
STOP_TIMEOUT = 5.0
_STATE_NAMESPACE = "monitor.gmail.history_ids"


class _HistoryExpired(Exception):
    pass


class GmailMonitor:
    def __init__(self, sources: list[GmailSource], project: str, state_store: MonitorStateStore):
        self._sources = sources
        self._project = project
        self._state_store = state_store
        self._topic = f"projects/{project}/topics/{GMAIL_PUBSUB_TOPIC}"
        self._subscription = f"projects/{project}/subscriptions/{GMAIL_PUBSUB_SUBSCRIPTION}"
        self._channel: Channel | None = None
        self._history_ids: dict[str, int] = {}
        self._email_to_source: dict[str, GmailSource] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._subscriber: pubsub_v1.SubscriberClient | None = None
        self._streaming_future = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: set[asyncio.Task] = set()
        self._stopping = False

    def start(self, channel: Channel) -> None:
        if self._stopping:
            self._stopping = False
        if self._loop and self._task_alive():
            return
        self._channel = channel
        self._loop = asyncio.get_running_loop()
        self._spawn_task(self._start_async())

    def _task_alive(self) -> bool:
        return any(not task.done() for task in self._tasks)

    def _spawn_task(self, coro: Coroutine[Any, Any, Any]) -> None:
        if self._stopping:
            coro.close()
            return
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _start_async(self) -> None:
        await self._restore_history_ids()
        new_ids = await asyncio.to_thread(self._setup_watches)
        for email, history_id in new_ids.items():
            # Never advance existing cursor on startup;
            # we may still need to backfill unseen history.
            self._history_ids.setdefault(email, history_id)
        await self._persist_history_ids()
        self._start_streaming_if_possible()
        self._spawn_task(self._watch_renewal_loop())

    async def stop(self) -> None:
        self._stopping = True

        if self._streaming_future:
            self._streaming_future.cancel()
            try:
                await asyncio.to_thread(self._streaming_future.result, timeout=STOP_TIMEOUT)
            except Exception:
                pass
            self._streaming_future = None

        # Yield to drain any pending call_soon_threadsafe callbacks
        # (they'll see _stopping and close their coroutines)
        await asyncio.sleep(0)

        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        if self._subscriber:
            subscriber = self._subscriber
            self._subscriber = None
            await asyncio.to_thread(subscriber.close)

    # --- Watch registration ---

    def _setup_watches(self) -> dict[str, int]:
        results: dict[str, int] = {}
        for src in self._sources:
            result = self._register_watch(src)
            if result:
                results[result[0]] = result[1]
        return results

    def _register_watch(self, src: GmailSource) -> tuple[str, int] | None:
        try:
            service = src._get_service()
            resp = (
                service.users()
                .watch(
                    userId="me",
                    body={"topicName": self._topic, "labelIds": ["INBOX"]},
                )
                .execute()
            )
            email = src.get_email_address().lower()
            history_id = int(resp["historyId"])
            self._email_to_source[email] = src
            _logger.info("Gmail watch registered for %s (historyId: %s)", email, history_id)
            return email, history_id
        except Exception:
            _logger.exception("Failed to register Gmail watch for %s", src.token_path)
            return None

    async def _watch_renewal_loop(self) -> None:
        while True:
            await asyncio.sleep(WATCH_RENEWAL_INTERVAL)
            _logger.info("Renewing Gmail watches")
            new_ids = await asyncio.to_thread(self._setup_watches)
            for email, history_id in new_ids.items():
                # Keep existing cursor to avoid skipping unseen history.
                self._history_ids.setdefault(email, history_id)
            await self._persist_history_ids()

    # --- Pub/Sub streaming ---

    def _start_streaming_if_possible(self) -> None:
        if not self._sources:
            _logger.warning("Gmail monitor has no sources; skipping streaming startup")
            return
        creds = self._sources[0]._get_credentials()
        self._subscriber = pubsub_v1.SubscriberClient(credentials=creds)
        self._streaming_future = self._subscriber.subscribe(
            self._subscription,
            callback=self._on_message,
        )
        _logger.info("Gmail monitor streaming from %s", self._subscription)

    def _on_message(self, message: pubsub_v1.subscriber.message.Message) -> None:
        try:
            data = json.loads(message.data.decode("utf-8"))
            email = data.get("emailAddress", "")
            history_id = int(data.get("historyId", 0))
        except Exception:
            _logger.warning("Invalid Gmail Pub/Sub message")
            message.ack()
            return

        if not email or not history_id:
            message.ack()
            return

        if self._loop is None:
            _logger.warning("No event loop for Gmail monitor; dropping notification for %s", email)
            message.nack()
            return

        try:
            self._loop.call_soon_threadsafe(
                self._spawn_task,
                self._process_message(message, email.lower(), history_id),
            )
        except RuntimeError:
            _logger.warning("Event loop closed; dropping Gmail notification for %s", email)
            message.nack()
            return

    # --- Notification processing ---

    async def _process_message(
        self,
        message: pubsub_v1.subscriber.message.Message,
        email: str,
        history_id: int,
    ) -> None:
        try:
            processed = await self._process_notification(email, history_id)
        except Exception:
            _logger.exception("Unhandled Gmail notification processing error for %s", email)
            processed = False

        if processed:
            message.ack()
        else:
            message.nack()

    async def _process_notification(self, email: str, history_id: int) -> bool:
        lock = self._locks.setdefault(email, asyncio.Lock())
        async with lock:
            last_id = self._history_ids.get(email)
            if not last_id:
                self._history_ids[email] = history_id
                await self._persist_history_ids()
                return True
            if history_id <= last_id:
                return True

            src = self._email_to_source.get(email)
            if not src:
                _logger.warning("No Gmail source for %s", email)
                return True

            try:
                msg_ids = await asyncio.to_thread(self._fetch_history, src, last_id)
            except _HistoryExpired:
                _logger.warning("History expired for %s, re-registering watch", email)
                result = await asyncio.to_thread(self._register_watch, src)
                if result:
                    self._history_ids[result[0]] = result[1]
                    await self._persist_history_ids()
                return True
            except Exception:
                _logger.exception("Failed to fetch Gmail history for %s", email)
                return False

            # Advance cursor only after successful fetch
            self._history_ids[email] = history_id
            await self._persist_history_ids()

            for msg_id in msg_ids:
                event = await asyncio.to_thread(self._build_event, src, msg_id)
                if event and self._channel:
                    self._channel.publish(event)
                    _logger.info("Published NewEmail: %s from %s", event.email_id, event.sender)
            return True

    def _fetch_history(self, src: GmailSource, start_history_id: int) -> list[str]:
        service = src._get_service()
        msg_ids: list[str] = []
        request = (
            service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                labelId="INBOX",
            )
        )
        while request is not None:
            try:
                response = request.execute()
            except HttpError as e:
                if e.resp.status == 404:
                    raise _HistoryExpired() from e
                raise
            for record in response.get("history", []):
                for added in record.get("messagesAdded", []):
                    msg = added.get("message", {})
                    if "INBOX" in msg.get("labelIds", []):
                        msg_ids.append(msg["id"])
            request = service.users().history().list_next(request, response)
        return msg_ids

    def _build_event(self, src: GmailSource, msg_id: str) -> NewEmail | None:
        msg = src._fetch_message_metadata(msg_id)
        if not msg:
            return None

        headers = extract_headers(msg.get("payload", {}).get("headers", []))
        return NewEmail(
            email_id=msg_id,
            subject=decode_email_header(headers.get("subject")) or "(no subject)",
            sender=decode_email_header(headers.get("from")) or "unknown",
            snippet=msg.get("snippet", ""),
            received_at=parse_email_date(
                msg.get("payload", {}).get("headers", []),
                int(msg.get("internalDate", 0)),
            ),
        )

    async def _restore_history_ids(self) -> None:
        payload = await self._state_store.get_state(_STATE_NAMESPACE)
        restored: dict[str, int] = {}
        for email, raw_id in payload.items():
            try:
                history_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if history_id > 0:
                restored[email.lower()] = history_id
        self._history_ids.update(restored)

    async def _persist_history_ids(self) -> None:
        await self._state_store.set_state(_STATE_NAMESPACE, self._history_ids)
