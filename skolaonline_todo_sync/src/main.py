"""
SkolaOnline ToDo Sync - Main entry point.

Reads configuration via bashio (Home Assistant addon options),
authenticates to SkolaOnline and iCloud Reminders via CalDAV,
then runs a per-pupil sync loop on the configured interval.

Config structure:
  pupils:
    - sol_name: "Surname Firstname"  # must match SkolaOnline Žák dropdown (surname-first)
      strategy: "parse_du"           # "single" or "parse_du"
      list_name: "Homework"          # reminder list name (CalDAV calendar)
      name_prefix: ""                # if non-empty, prefix all titles with "[name_prefix] "
"""
import logging
import signal
import sys
import threading

import bashio

from skolaonline import SkolaOnlineClient
from icloud_reminders import ICloudRemindersClient
from sync import sync_homework, STRATEGY_SINGLE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

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
    sol_username = bashio.config("skolaonline_username")
    sol_password = bashio.config("skolaonline_password")
    sync_interval = int(bashio.config("sync_interval"))
    raw_pupils = bashio.config("pupils") or []

    # Build pupil config list
    pupils_cfg = []
    for entry in raw_pupils:
        pupils_cfg.append({
            "sol_name": entry["sol_name"],
            "strategy": entry.get("strategy") or STRATEGY_SINGLE,
            "list_name": entry.get("list_name") or "Homework",
            "name_prefix": entry.get("name_prefix") or "",
            "include_past": bool(entry.get("include_past", True)),
        })

    if not pupils_cfg:
        log.error("No pupils configured. Add at least one entry under 'pupils' in the addon config.")
        sys.exit(1)

    skola = SkolaOnlineClient(username=sol_username, password=sol_password)

    backend = ICloudRemindersClient(
        apple_id=bashio.config("icloud_apple_id"),
        app_password=bashio.config("icloud_app_password"),
        uid_map_path="/data/icloud_uid_map.json",
    )
    log.info("Authenticating to iCloud CalDAV...")
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
                )
            except Exception:
                log.exception("Sync failed for pupil %r, will retry next interval.", pupil["sol_name"])

        log.info("All pupils synced. Next run in %d minutes.", sync_interval)
        _shutdown.wait(timeout=interval_seconds)

    log.info("Stopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()
