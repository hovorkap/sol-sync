"""
Sync logic: maps SkolaOnline homework assignments to a reminder backend.

Supported backends:
  - icloud   → icloud_reminders.ICloudRemindersClient
  - microsoft → microsoft_todo.MicrosoftToDoClient

Supported sync strategies:
  - single    (default) — one reminder per SkolaOnline homework record.
  - parse_du  — parse "DÚ" lines from the description and create one reminder
                per DÚ line. Lines not starting with "DÚ" (e.g. lesson notes)
                are ignored. Useful when teachers mix homework and class notes
                in a single SkolaOnline entry.

Deduplication:
  - Every reminder is identified by a stable UID embedded in the iCalendar
    VTODO UID (iCloud) or task title prefix "[SO-...]" (Microsoft To Do).
  - UIDs are scoped per-pupil using osoba_id to prevent collisions when two
    pupils share the same reminder list.
  - `single` UID:    "SO-{osoba_id}-{ukol_id}"
  - `parse_du` UID:  "SO-{osoba_id}-{ukol_id}-du-{sha1(normalized_title)[:8]}"
    Content-hash based so ordering/insertion changes don't create duplicates.

Name prefix:
  - If name_prefix is a non-empty string, all reminder titles are prefixed
    with "[name_prefix] " (e.g. "[Maxim] M PS 50/4").
  - Useful when two pupils sync to the same reminder list.
"""
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional, Union

from skolaonline import HomeworkAssignment, SkolaOnlineClient

log = logging.getLogger(__name__)

STRATEGY_SINGLE = "single"
STRATEGY_PARSE_DU = "parse_du"


@dataclass
class ReminderItem:
    uid: str
    title: str
    description: str
    due_date: Optional[date]


# ---------------------------------------------------------------------------
# Public sync entry point
# ---------------------------------------------------------------------------

def sync_homework(
    skola: SkolaOnlineClient,
    backend,   # ICloudRemindersClient | GenericCalDAVClient
    list_name: str,
    strategy: str = STRATEGY_SINGLE,
    pupil_value: Optional[str] = None,
    name_prefix: str = "",
    include_past: bool = True,
    reminder_time: Optional[str] = None,
) -> None:
    """
    Fetch homework from SkolaOnline and create missing reminders via backend.

    pupil_value:  dropdown option value from SkolaOnlineClient.get_pupils();
                  if given, filters homework for that pupil only.
    name_prefix:  if non-empty, prepend "[name_prefix] " to all reminder titles.
                  Use when two pupils share the same reminder list.
    include_past: if False, skip assignments whose due_date is before today.
                  Assignments with no due_date are always included.
    reminder_time: "HH:MM" string (e.g. "18:00"). When set, DUE is written as
                  a floating datetime and a VALARM fires at that time.

    backend must expose:
      - get_or_create_list(name) → list_handle
      - get_task_uids(list_handle) → set[str]
      - create_task(list_handle, uid, title, description, due_date, reminder_time)
    """
    assignments = skola.get_homework(pupil_value=pupil_value)
    if not assignments:
        log.info("No homework assignments found.")
        return

    log.info("Found %d homework assignment(s) in total.", len(assignments))

    if not include_past:
        today = date.today()
        before = len(assignments)
        assignments = [
            a for a in assignments
            if a.due_date is None or a.due_date >= today
        ]
        log.info(
            "Past filter: keeping %d of %d assignments (due today or later).",
            len(assignments), before,
        )

    list_handle = backend.get_or_create_list(list_name)
    existing_uids = _get_existing_uids(backend, list_handle)

    created = 0
    for assignment in assignments:
        # Determine which reminder items to create for this assignment
        candidate_uids = _candidate_uids(assignment, strategy)
        if all(uid in existing_uids for uid in candidate_uids):
            log.debug("Skipping already-synced assignment %s.", assignment.id)
            continue

        # Fetch description only for new assignments
        try:
            description = skola.get_assignment_description(assignment.id)
        except Exception:
            log.warning("Could not fetch description for %s.", assignment.id)
            description = ""

        items = _build_reminder_items(assignment, description, strategy, name_prefix)
        for item in items:
            if item.uid in existing_uids:
                continue
            log.info(
                "Adding to '%s': %s (due: %s)",
                list_name,
                item.title,
                item.due_date.isoformat() if item.due_date else "no date",
            )
            _create_via_backend(backend, list_handle, item, reminder_time)
            existing_uids.add(item.uid)
            created += 1

    log.info("Sync complete: %d new reminder(s) created.", created)


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

def _candidate_uids(assignment: HomeworkAssignment, strategy: str) -> list[str]:
    """Return the UIDs that WOULD be created for this assignment (without fetching description)."""
    # For both strategies, use the base assignment UID as a proxy — if it exists,
    # skip the description fetch. The inner loop handles fine-grained deduplication.
    return [_base_uid(assignment)]


def _base_uid(assignment: HomeworkAssignment) -> str:
    return f"SO-{assignment.osoba_id}-{assignment.id}"


def _build_reminder_items(
    assignment: HomeworkAssignment,
    description: str,
    strategy: str,
    name_prefix: str = "",
) -> list[ReminderItem]:
    if strategy == STRATEGY_PARSE_DU:
        return _parse_du_items(assignment, description, name_prefix)
    return [_single_item(assignment, description, name_prefix)]


def _single_item(
    assignment: HomeworkAssignment,
    description: str,
    name_prefix: str = "",
) -> ReminderItem:
    subject_part = f" [{assignment.subject}]" if assignment.subject else ""
    title = f"{subject_part} {assignment.title}".strip()
    if name_prefix:
        title = f"[{name_prefix}] {title}"
    return ReminderItem(
        uid=_base_uid(assignment),
        title=title,
        description=description,
        due_date=assignment.due_date,
    )


def _parse_du_items(
    assignment: HomeworkAssignment,
    description: str,
    name_prefix: str = "",
) -> list[ReminderItem]:
    """
    Extract DÚ (Domácí Úkol = homework) lines from the description.

    Lines starting with "DÚ" (case-insensitive, after stripping leading
    whitespace) are homework items. All other lines are lesson notes and
    are ignored.

    UID is content-hash based to stay stable if the teacher edits the order
    or adds/removes other lines.
    """
    items: list[ReminderItem] = []
    for line in description.splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("DÚ") and not stripped.upper().startswith("DU"):
            continue

        # Strip "DÚ -", "DÚ–", "DÚ:", "DÚ " prefixes (separator is optional)
        title = re.sub(r'^D[ÚU]\s*[-–:]?\s*', '', stripped, flags=re.IGNORECASE).rstrip(';').strip()
        if not title:
            continue

        # Hash the normalized title for a stable, order-independent UID
        normalized = title.lower().strip()
        uid_hash = hashlib.sha1(normalized.encode()).hexdigest()[:8]
        uid = f"{_base_uid(assignment)}-du-{uid_hash}"

        if name_prefix:
            title = f"[{name_prefix}] {title}"

        items.append(ReminderItem(
            uid=uid,
            title=title,
            description="",
            due_date=assignment.due_date,
        ))

    if not items:
        # Fall back to single item if no DÚ lines found (e.g. pure class notes entry)
        log.debug("No DÚ lines found for %s, falling back to single item.", assignment.id)
        items = [_single_item(assignment, description, name_prefix)]

    return items


# ---------------------------------------------------------------------------
# Backend abstraction helpers
# ---------------------------------------------------------------------------

def _get_existing_uids(backend, list_handle) -> set[str]:
    """Return existing task UIDs regardless of backend type."""
    if hasattr(backend, "get_task_uids"):
        # ICloudRemindersClient
        return backend.get_task_uids(list_handle)
    # MicrosoftToDoClient — extract uid from "[SO-...]" title prefix
    tasks = backend.get_tasks(list_handle)
    uids = set()
    for task in tasks:
        uid = _extract_ms_uid(task.get("title", ""))
        if uid:
            uids.add(uid)
    return uids


def _extract_ms_uid(title: str) -> Optional[str]:
    """Extract 'SO-...' from a Microsoft To Do task title like '[SO-...] ...'."""
    m = re.match(r'^\[SO-([^\]]+)\]', title)
    return f"SO-{m.group(1)}" if m else None


def _create_via_backend(backend, list_handle, item: ReminderItem, reminder_time: Optional[str] = None) -> None:
    """Create a reminder via either backend."""
    backend.create_task(
        list_handle,
        uid=item.uid,
        title=item.title,
        description=item.description,
        due_date=item.due_date,
        reminder_time=reminder_time,
    )
