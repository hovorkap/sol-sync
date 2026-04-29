## 0.25.1

### Fixed
- After dismissing the unread messages modal, do a fresh GET of the homework page before continuing. This ensures subsequent postbacks use a clean, valid page state regardless of what the dismiss POST returned.

## 0.25.0

### Fixed
- Automatically dismiss the "unread messages" modal dialog (`Nepřečtené zprávy`) that SkolaOnline shows after login. The modal is now detected and silently dismissed via the "read later" button before scraping homework, so it no longer blocks data synchronization.

## 0.24.0

### Changed
- Screenshot added to documentation (shown at bottom of HA addon panel and in GitHub README)
- Fixed `reminder_time` description — clarified that the notification fires the **evening before** the due date, not on the due date itself
- README and DOCS updated with missing `reminder_time` option

## 0.23.0

### Changed
- Add-on renamed to **SkolaOnline CalDAV Sync** to better reflect that it supports any CalDAV server, not just iCloud

## 0.22.1

### Fixed
- Reminder alarm now fires the **evening before** the due date (not on the due date itself). DUE remains set to the actual due date; the VALARM uses an absolute `TRIGGER;VALUE=DATE-TIME` set to `(due_date - 1 day)` at the configured time.



### Added
- `reminder_time` config option (e.g. `"18:00"`): when set, the due date on each reminder becomes a datetime and a VALARM is added so the phone pops a notification at that time on the due date. Leave empty to keep date-only behaviour (no notification).



### Added
- CHANGELOG.md — version history now visible in HA addon info panel

## 0.20.0

### Changed
- Documentation fully aligned with configuration: README updated with `cal_backend`, `caldav_*`, and `default_list_name` options; example config updated
- Czech DOCS.md: improved `list_name` and `include_past` descriptions

## 0.19.0

### Added
- **Generic CalDAV backend** — works with any standard CalDAV server (Nextcloud, Radicale, Baikal, etc.)
- New `cal_backend` option: `icloud` (default, backward compatible) or `caldav`
- New options for generic backend: `caldav_url`, `caldav_username`, `caldav_password`
- Czech UI translations (`translations/cs.yaml`) — config labels shown in Czech when HA language is set to Czech
- English UI translations (`translations/en.yaml`)
- Czech `DOCS.md` — documentation shown in the HA addon info panel

## 0.18.0

### Fixed
- Add-on now starts correctly in Home Assistant — root cause was a custom AppArmor profile blocking `/bin/sh` and `/run.sh`
- Dockerfile now follows the official HA tutorial pattern: `COPY run.sh /` + `CMD ["/run.sh"]`
- Removed overly restrictive custom AppArmor profile; HA default profile is sufficient

## 0.12.0

### Added
- New top-level `default_list_name` option — set the reminder list name once at the root level; can be overridden per pupil
- Per-pupil `list_name` is now optional (falls back to `default_list_name`)

## 0.10.0

### Added
- Detailed sync logging: total homework count, number of new items, each added item logged with list name and due date

## 0.4.0

### Fixed
- Add-on configuration is now read directly from `/data/options.json` — removes dependency on `bashio` in Python code
- Add-on schema fixed to use correct HA syntax for enums and optional fields
- Repository structure aligned with HA add-on store requirements

## 0.3.0

### Added
- Initial release
- SkolaOnline homework scraping (login, pagination, pupil dropdown, description lazy-fetch)
- iCloud Reminders sync via CalDAV with UUID mapping to avoid iCloud UID conflicts
- Multi-pupil support with per-pupil reminder list, sync strategy, and name prefix
- Two sync strategies: `single` (one item per assignment) and `parse_du` (parses individual homework lines from description)
- Configurable sync interval
- Graceful shutdown on SIGTERM
