"""
Generic CalDAV VTODO client.

Works with any standard CalDAV server (Nextcloud, Radicale, Baikal, etc.).
Unlike the iCloud client, this uses logical UIDs directly — no UUID remapping.

Authentication is Basic Auth (username + password). The server URL must
point to the CalDAV root (e.g. https://nextcloud.example.com/remote.php/dav).
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import caldav

log = logging.getLogger(__name__)


class GenericCalDAVClient:
    """CalDAV client for any standard VTODO-capable CalDAV server."""

    def __init__(self, url: str, username: str, password: str):
        self._url = url
        self._username = username
        self._password = password
        self._client: Optional[caldav.DAVClient] = None
        self._principal: Optional[caldav.Principal] = None

    def authenticate(self) -> None:
        """Connect to the CalDAV server and verify credentials."""
        log.info("Connecting to CalDAV server at %s as %s...", self._url, self._username)
        self._client = caldav.DAVClient(
            url=self._url,
            username=self._username,
            password=self._password,
        )
        try:
            self._principal = self._client.principal()
        except Exception as e:
            raise RuntimeError(
                f"CalDAV authentication failed for {self._url}: {e}"
            ) from e
        log.info("Connected to CalDAV server.")

    def get_or_create_list(self, list_name: str) -> caldav.Calendar:
        """
        Return the VTODO calendar matching list_name, creating it if needed.
        """
        assert self._principal is not None, "Call authenticate() first"

        for cal in self._principal.calendars():
            if not self._supports_vtodo(cal):
                continue
            if (cal.name or "").lower() == list_name.lower():
                log.debug("Found existing calendar: %r", cal.name)
                return cal

        log.info("Calendar %r not found, creating it...", list_name)
        return self._principal.make_calendar(
            name=list_name,
            supported_calendar_component_set=["VTODO"],
        )

    def get_task_uids(self, calendar: caldav.Calendar) -> set[str]:
        """Return the set of UIDs for all VTODO items in the calendar."""
        uids: set[str] = set()
        try:
            for todo in calendar.todos(include_completed=True):
                uid = str(todo.icalendar_component.get("UID", ""))
                if uid:
                    uids.add(uid)
        except Exception:
            log.exception("Failed to fetch existing task UIDs.")
        return uids

    def create_task(
        self,
        calendar: caldav.Calendar,
        uid: str,
        title: str,
        description: str,
        due_date: Optional[date] = None,
        reminder_time: Optional[str] = None,
    ) -> None:
        """Create a VTODO in the given calendar using the logical UID directly.

        reminder_time: "HH:MM" string (e.g. "18:00"). When set, the DUE is
        written as a floating datetime and a VALARM is added so the device
        pops a notification at that time.
        """
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        due_line = ""
        alarm_block = ""
        if due_date:
            due_line = f"DUE;VALUE=DATE:{due_date.strftime('%Y%m%d')}\r\n"
            if reminder_time:
                try:
                    hh, mm = reminder_time.split(":")
                    # Fire the alarm the evening BEFORE the due date
                    alarm_dt = due_date - timedelta(days=1)
                    alarm_str = f"{alarm_dt.strftime('%Y%m%d')}T{int(hh):02d}{int(mm):02d}00"
                    alarm_block = (
                        "BEGIN:VALARM\r\n"
                        "ACTION:DISPLAY\r\n"
                        "DESCRIPTION:Reminder\r\n"
                        f"TRIGGER;VALUE=DATE-TIME:{alarm_str}\r\n"
                        "END:VALARM\r\n"
                    )
                except (ValueError, AttributeError):
                    log.warning("Invalid reminder_time %r, skipping alarm.", reminder_time)

        ical = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//SkolaOnlineToDoSync//EN\r\n"
            "BEGIN:VTODO\r\n"
            f"UID:{uid}\r\n"
            f"DTSTAMP:{now}\r\n"
            f"{_fold_ical_line(f'SUMMARY:{_escape_ical(title)}')}\r\n"
            f"{_fold_ical_line(f'DESCRIPTION:{_escape_ical(description)}')}\r\n"
            f"{due_line}"
            "STATUS:NEEDS-ACTION\r\n"
            f"{alarm_block}"
            "END:VTODO\r\n"
            "END:VCALENDAR\r\n"
        )
        calendar.save_todo(ical)
        log.debug("Created task uid=%s: %r", uid, title[:60])

    @staticmethod
    def _supports_vtodo(calendar: caldav.Calendar) -> bool:
        try:
            return "VTODO" in calendar.get_supported_components()
        except Exception:
            return False


def _escape_ical(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
        .replace("\r", "")
        .replace("\xa0", " ")
    )


def _fold_ical_line(line: str) -> str:
    """Fold a single iCalendar content line per RFC 5545 §3.1."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts = []
    while encoded:
        chunk = encoded[:75]
        while chunk:
            try:
                chunk.decode("utf-8")
                break
            except UnicodeDecodeError:
                chunk = chunk[:-1]
        parts.append(chunk.decode("utf-8"))
        encoded = encoded[len(chunk):]
    return "\r\n ".join(parts)
