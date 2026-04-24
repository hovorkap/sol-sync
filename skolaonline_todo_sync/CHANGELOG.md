## 0.21.0

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
