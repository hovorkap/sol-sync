"""
SkolaOnline ToDo Sync - Main entry point.

Reads configuration from /data/options.json (Home Assistant addon options),
authenticates to SkolaOnline and iCloud Reminders via CalDAV,
then runs a per-pupil sync loop on the configured interval.

Config structure:
  pupils:
    - sol_name: "Surname Firstname"  # must match SkolaOnline Žák dropdown (surname-first)
      strategy: "parse_du"           # "single" or "parse_du"
      list_name: "Homework"          # reminder list name (CalDAV calendar)
      name_prefix: ""                # if non-empty, prefix all titles with "[name_prefix] "
"""
import json
import logging
import os
import signal
import sys
import threading

from skolaonline import SkolaOnlineClient
from icloud_reminders import ICloudRemindersClient
from generic_caldav import GenericCalDAVClient
from sync import sync_homework, STRATEGY_SINGLE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

_OPTIONS_PATH = "/data/options.json"


def _load_options() -> dict:
    with open(_OPTIONS_PATH) as f:
        return json.load(f)


def config(key, options: dict):
    return options.get(key)

_shutdown = threading.Event()


def _handle_sigterm(signum, frame):
    log.info("Received SIGTERM, shutting down...")
    _shutdown.set()


signal.signal(signal.SIGTERM, _handle_sigterm)


def _resolve_pupils(skola: SkolaOnlineClient, configured_pupils: list[dict]) -> list[dict]:
    """
    Match each configured pupil entry against the live SkolaOnline dropdown.

    Returns the same list enriched with 'pupil_value' (the dropdown option value).
    Logs available names and exits if any configured pupil cannot be matched.
    """
    available = skola.get_pupils()
    available_names = [p.display_name for p in available]

    if not available:
        log.warning("No pupils found in SkolaOnline dropdown; proceeding without pupil filter.")
        for entry in configured_pupils:
            entry["pupil_value"] = None
        return configured_pupils

    resolved = []
    for entry in configured_pupils:
        sol_name = entry["sol_name"]
        # Normalize whitespace for comparison
        normalized = " ".join(sol_name.split())
        match = next(
            (p for p in available if " ".join(p.display_name.split()) == normalized),
            None,
        )
        if match is None:
            log.error(
                "Configured pupil %r not found in SkolaOnline. Available: %s",
                sol_name,
                available_names,
            )
            sys.exit(1)
        log.info("Resolved pupil %r → dropdown value %r", sol_name, match.value)
        resolved.append({**entry, "pupil_value": match.value})

    return resolved


def main():
    options = _load_options()

    sol_username = options["skolaonline_username"]
    sol_password = options["skolaonline_password"]
    sync_interval = int(options.get("sync_interval", 30))
    default_list_name = options.get("default_list_name") or "Homework"
    reminder_time = options.get("reminder_time") or None
    raw_pupils = options.get("pupils") or []

    # Build pupil config list — list_name falls back to default_list_name if not set per-pupil
    pupils_cfg = []
    for entry in raw_pupils:
        pupils_cfg.append({
            "sol_name": entry["sol_name"],
            "strategy": entry.get("strategy") or STRATEGY_SINGLE,
            "list_name": entry.get("list_name") or default_list_name,
            "name_prefix": entry.get("name_prefix") or "",
            "include_past": bool(entry.get("include_past", False)),
        })

    if not pupils_cfg:
        log.error("No pupils configured. Add at least one entry under 'pupils' in the addon config.")
        sys.exit(1)

    skola = SkolaOnlineClient(username=sol_username, password=sol_password)

    cal_backend = options.get("cal_backend") or "icloud"
    if cal_backend == "icloud":
        apple_id = options.get("icloud_apple_id") or ""
        app_password = options.get("icloud_app_password") or ""
        if not apple_id or not app_password:
            log.error("iCloud backend requires icloud_apple_id and icloud_app_password.")
            sys.exit(1)
        backend = ICloudRemindersClient(
            apple_id=apple_id,
            app_password=app_password,
            uid_map_path="/data/icloud_uid_map.json",
        )
        log.info("Authenticating to iCloud CalDAV...")
    elif cal_backend == "caldav":
        caldav_url = options.get("caldav_url") or ""
        caldav_username = options.get("caldav_username") or ""
        caldav_password = options.get("caldav_password") or ""
        if not caldav_url or not caldav_username:
            log.error("CalDAV backend requires caldav_url and caldav_username.")
            sys.exit(1)
        backend = GenericCalDAVClient(
            url=caldav_url,
            username=caldav_username,
            password=caldav_password,
        )
        log.info("Authenticating to CalDAV server %s...", caldav_url)
    else:
        log.error("Unknown cal_backend %r. Must be 'icloud' or 'caldav'.", cal_backend)
        sys.exit(1)

    backend.authenticate()

    # Resolve dropdown values for all configured pupils once at startup
    pupils = _resolve_pupils(skola, pupils_cfg)
    for p in pupils:
        log.info(
            "Pupil: %r | strategy: %s | list: %r | prefix: %r | include_past: %s",
            p["sol_name"], p["strategy"], p["list_name"],
            p["name_prefix"] or "(none)", p["include_past"],
        )

    interval_seconds = sync_interval * 60

    while not _shutdown.is_set():
        for pupil in pupils:
            try:
                log.info("Syncing pupil %r...", pupil["sol_name"])
                sync_homework(
                    skola,
                    backend,
                    list_name=pupil["list_name"],
                    strategy=pupil["strategy"],
                    pupil_value=pupil["pupil_value"],
                    name_prefix=pupil["name_prefix"],
                    include_past=pupil["include_past"],
                    reminder_time=reminder_time,
                )
            except Exception:
                log.exception("Sync failed for pupil %r, will retry next interval.", pupil["sol_name"])

        log.info("All pupils synced. Next run in %d minutes.", sync_interval)
        _shutdown.wait(timeout=interval_seconds)

    log.info("Stopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()
