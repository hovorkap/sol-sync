"""
iCloud Reminders client via CalDAV.

iCloud Reminders are VTODO components accessible over CalDAV at
https://caldav.icloud.com.

Authentication requires an Apple ID and an **app-specific password**
(generated at https://appleid.apple.com > Security > App-Specific Passwords).
Regular Apple ID passwords do NOT work due to 2FA enforcement.

iCloud CalDAV quirks:
  - Service discovery must go through the principal URL, not a well-known URL.
  - Not all calendar collections support VTODO; filter explicitly.
  - Creating a list requires specifying supported_calendar_component_set=["VTODO"].
  - Family shared reminder lists appear as regular calendars in the principal's
    calendar home; find them by display name.
  - iCloud maintains a GLOBAL UID index across ALL calendars, including deleted
    ones. If you delete a calendar and recreate it, the old UIDs are locked for
    an unknown period. To work around this, we use random UUID4s for the actual
    iCloud VTODO UIDs and maintain a local {logical_uid → icloud_uuid} mapping
    in a JSON file. If a PUT returns 412 (UID conflict), we generate a fresh
    UUID4 and retry once.
"""
import json
import logging
import os
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import caldav

log = logging.getLogger(__name__)

ICLOUD_CALDAV_URL = "https://caldav.icloud.com"
_DEFAULT_UID_MAP_PATH = "/data/icloud_uid_map.json"


class ICloudRemindersClient:
    """CalDAV client for iCloud Reminders (VTODO)."""

    def __init__(
        self,
        apple_id: str,
        app_password: str,
        uid_map_path: str = _DEFAULT_UID_MAP_PATH,
    ):
        self._apple_id = apple_id
        self._app_password = app_password
        self._uid_map_path = uid_map_path
        self._client: Optional[caldav.DAVClient] = None
        self._principal: Optional[caldav.Principal] = None
        # logical_uid → icloud_uuid (str)
        self._uid_map: dict[str, str] = {}

    def authenticate(self) -> None:
        """Connect to iCloud CalDAV and verify credentials."""
        log.info("Connecting to iCloud CalDAV as %s...", self._apple_id)
        self._client = caldav.DAVClient(
            url=ICLOUD_CALDAV_URL,
            username=self._apple_id,
            password=self._app_password,
        )
        try:
            self._principal = self._client.principal()
        except Exception as e:
            raise RuntimeError(
                f"iCloud CalDAV authentication failed. "
                f"Make sure you're using an app-specific password: {e}"
            ) from e
        self._load_uid_map()
        log.info("Connected to iCloud CalDAV.")

    def get_or_create_list(self, list_name: str) -> caldav.Calendar:
        """
        Return the VTODO calendar (reminder list) matching list_name.

        Searches the principal's calendar home for a VTODO-capable calendar
        with a matching display name (case-insensitive). Creates one if not found.
        """
        assert self._principal is not None, "Call authenticate() first"

        calendars = self._principal.calendars()
        for cal in calendars:
            if not self._supports_vtodo(cal):
                continue
            name = cal.name or ""
            if name.lower() == list_name.lower():
                log.debug("Found existing reminder list: %r", name)
                return cal

        log.info("Reminder list %r not found, creating it...", list_name)
        new_cal = self._principal.make_calendar(
            name=list_name,
            supported_calendar_component_set=["VTODO"],
        )
        return new_cal

    def get_task_uids(self, calendar: caldav.Calendar) -> set[str]:
        """
        Return the set of logical UIDs for all VTODO items in the calendar.

        Fetches the iCloud UUID from each todo, then reverse-maps via the
        local uid_map to recover logical UIDs. Todos whose iCloud UUID is not
        in the map (e.g. created outside this app) are ignored.
        """
        reverse_map = {v: k for k, v in self._uid_map.items()}
        uids: set[str] = set()
        try:
            todos = calendar.todos(include_completed=True)
            for todo in todos:
                icloud_uid = str(todo.icalendar_component.get("UID", ""))
                logical_uid = reverse_map.get(icloud_uid)
                if logical_uid:
                    uids.add(logical_uid)
        except Exception:
            log.exception("Failed to fetch existing reminder UIDs.")
        return uids

    def create_task(
        self,
        calendar: caldav.Calendar,
        uid: str,
        title: str,
        description: str,
        due_date: Optional[date] = None,
    ) -> None:
        """
        Create a VTODO (reminder) in the given calendar.

        Uses a random UUID4 as the iCloud UID (stored in uid_map) to avoid
        iCloud's global UID conflict. If the PUT returns 412 (conflict), a
        fresh UUID4 is generated and the operation is retried once.
        """
        icloud_uid = self._get_or_create_icloud_uid(uid)
        try:
            self._put_todo(calendar, icloud_uid, title, description, due_date)
        except caldav.lib.error.PutError as e:
            if "412" in str(e):
                log.warning(
                    "iCloud UID conflict for %s (412), generating fresh UUID and retrying.",
                    uid,
                )
                icloud_uid = str(uuid.uuid4())
                self._uid_map[uid] = icloud_uid
                self._save_uid_map()
                self._put_todo(calendar, icloud_uid, title, description, due_date)
            else:
                raise

        log.debug("Created reminder logical=%s icloud=%s: %r", uid, icloud_uid, title[:60])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_icloud_uid(self, logical_uid: str) -> str:
        """Return the iCloud UUID for a logical UID, creating one if needed."""
        if logical_uid not in self._uid_map:
            self._uid_map[logical_uid] = str(uuid.uuid4())
            self._save_uid_map()
        return self._uid_map[logical_uid]

    def _put_todo(
        self,
        calendar: caldav.Calendar,
        icloud_uid: str,
        title: str,
        description: str,
        due_date: Optional[date],
    ) -> None:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        due_line = ""
        if due_date:
            due_line = f"DUE;VALUE=DATE:{due_date.strftime('%Y%m%d')}\r\n"

        ical = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//SkolaOnlineToDoSync//EN\r\n"
            "BEGIN:VTODO\r\n"
            f"UID:{icloud_uid}\r\n"
            f"DTSTAMP:{now}\r\n"
            f"{_fold_ical_line(f'SUMMARY:{_escape_ical(title)}')}\r\n"
            f"{_fold_ical_line(f'DESCRIPTION:{_escape_ical(description)}')}\r\n"
            f"{due_line}"
            "STATUS:NEEDS-ACTION\r\n"
            "END:VTODO\r\n"
            "END:VCALENDAR\r\n"
        )
        calendar.save_todo(ical)

    def _load_uid_map(self) -> None:
        try:
            with open(self._uid_map_path) as f:
                self._uid_map = json.load(f)
            log.debug("Loaded %d UID mappings from %s", len(self._uid_map), self._uid_map_path)
        except FileNotFoundError:
            self._uid_map = {}
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Could not load UID map from %s: %s", self._uid_map_path, e)
            self._uid_map = {}

    def _save_uid_map(self) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._uid_map_path)), exist_ok=True)
            with open(self._uid_map_path, "w") as f:
                json.dump(self._uid_map, f, indent=2)
        except OSError as e:
            log.warning("Could not save UID map to %s: %s", self._uid_map_path, e)

    @staticmethod
    def _supports_vtodo(calendar: caldav.Calendar) -> bool:
        """Return True if the calendar supports VTODO components."""
        try:
            component_set = calendar.get_supported_components()
            return "VTODO" in component_set
        except Exception:
            return False


def _escape_ical(text: str) -> str:
    """Escape special characters for iCalendar text values."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
        .replace("\r", "")
        .replace("\xa0", " ")  # non-breaking space common in Czech web content
    )


def _fold_ical_line(line: str) -> str:
    """
    Fold a single iCalendar content line per RFC 5545 §3.1.

    Lines must not exceed 75 octets (bytes). Continuation lines start
    with a single SPACE. Multi-byte UTF-8 characters are never split.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line

    parts = []
    while encoded:
        # Take up to 75 bytes but never cut a multi-byte sequence
        chunk = encoded[:75]
        # Walk back until the chunk is valid UTF-8
        while chunk:
            try:
                chunk.decode("utf-8")
                break
            except UnicodeDecodeError:
                chunk = chunk[:-1]
        parts.append(chunk.decode("utf-8"))
        encoded = encoded[len(chunk):]

    return "\r\n ".join(parts)
