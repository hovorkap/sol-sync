# Copilot Instructions – SkolaOnline Sync

## Project overview

Home Assistant addon that synchronizes homework assignments from **SkolaOnline.cz** (Czech school parent portal) to a **CalDAV calendar** — iCloud Reminders or any standard CalDAV server (Nextcloud, Radicale, Baikal, etc.).

This is a **GitHub add-on repository** for Home Assistant. Users add the repo URL to HA and install the addon from there.

## Repository layout

```
repository.yaml                    # HA add-on repository metadata
README.md
CHANGELOG.md                       # root-level (not used by HA)
skolaonline_caldav_sync/
  config.yaml                      # HA addon manifest (name, slug, options, schema, arch)
  Dockerfile                       # FROM ghcr.io/home-assistant/base:latest, apk python3
  run.sh                           # #!/bin/sh entry point — exec python3 /app/main.py
  CHANGELOG.md                     # HA addon changelog (shown in HA UI)
  DOCS.md                          # Czech documentation (shown in HA addon info panel)
  README.md                        # English documentation (shown on GitHub)
  translations/
    en.yaml                        # English config option labels for HA UI
    cs.yaml                        # Czech config option labels for HA UI
  src/
    main.py                        # Reads /data/options.json, runs sync loop
    skolaonline.py                 # SkolaOnline HTTP/scraping client
    icloud_reminders.py            # iCloud Reminders CalDAV client (UUID mapping quirk)
    generic_caldav.py              # Generic CalDAV client (Nextcloud, Radicale, etc.)
    sync.py                        # Homework → reminder mapping, strategy logic
    requirements.txt
```

## Architecture

**Data flow:** `main.py` reads config → `SkolaOnlineClient.login()` → `SkolaOnlineClient.get_homework()` → `sync_homework()` → backend `create_task()`.

**Auth:**
- SkolaOnline: HTTP session with plain POST login (no ViewState)
- iCloud: CalDAV Basic Auth with Apple ID + app-specific password (from appleid.apple.com)
- Generic CalDAV: Basic Auth with username + password against a user-provided URL

**Backend selection:** `cal_backend` config option (`icloud` or `caldav`).
- `icloud` uses `icloud_reminders.ICloudRemindersClient` (CalDAV/VTODO with UUID remapping)
- `caldav` uses `generic_caldav.GenericCalDAVClient` (standard CalDAV, no UUID quirks)
- Both expose the same interface: `authenticate()`, `get_or_create_list()`, `get_task_uids()`, `create_task()`

**Pupil abstraction:**
- The homework page has a `Žák` (pupil) dropdown: `ctl00$listOfChildrenPart$listOfChildren$DDLChildren`
- Value format: `{ORG_ID}#{OSOBA_ID}` (e.g. `C1057#C3449720`). Display text: `"Příjmení Jméno"` (surname-first).
- `SkolaOnlineClient.get_pupils() -> list[Pupil]` — parses the dropdown. `Pupil(display_name, value)`.
- `SkolaOnlineClient.get_homework(pupil_value=None)` — if `pupil_value` given, fires a pupil-selection postback before the "show completed" postback. Always does a fresh GET for each pupil to avoid stale ASP.NET page state.
- **Always do a fresh GET per pupil sync** — do not reuse soup state across pupils.

**Per-pupil config (`pupils` list in config.yaml):**
```yaml
pupils:
  - sol_name: "Hovorka Maxim"   # exact dropdown text (whitespace-normalized for matching)
    strategy: "parse_du"        # "single" or "parse_du"
    list_name: ""               # overrides default_list_name if non-empty
    name_prefix: "Maxim"        # if non-empty, prefix all titles with "[Maxim] "
    include_past: false
```
`name_prefix` is an explicit string (not derived). Use it when two pupils share the same `list_name` to distinguish their items.

**UID scoping:** UIDs include `osoba_id` (the pupil's person ID from col 4) to prevent collisions:
- `single`: `SO-{osoba_id}-{ukol_id}`
- `parse_du`: `SO-{osoba_id}-{ukol_id}-du-{sha1_hash}`

**Polling loop:** `main.py` uses `threading.Event.wait(timeout=interval_seconds)` to sleep between syncs. A `SIGTERM` handler sets the event to trigger a clean shutdown.

## Key conventions

### Changelog (IMPORTANT)
- **Always update `skolaonline_caldav_sync/CHANGELOG.md`** when making user-facing changes.
- Add a new `## X.Y.Z` section at the top with `### Added`, `### Changed`, or `### Fixed` subsections.
- The changelog version must match the version in `config.yaml`.
- Do not add changelog entries for pure documentation or internal refactoring changes unless they affect users.

### Home Assistant addon constraints
- Configuration is read directly from `/data/options.json` via `json.load()` — not bashio, not env vars.
- Persistent state goes in `/data/`. This directory survives addon restarts.
- Log to stdout/stderr only. Use Python `logging` — never write to log files.
- `run.sh` uses `#!/bin/sh` (not `with-contenv bashio`) and simply does `exec python3 /app/main.py`.
- When adding new user-facing config options, update **all four** of: `options:` in `config.yaml`, `schema:` in `config.yaml`, `translations/en.yaml`, `translations/cs.yaml`.
- The HA addon `CHANGELOG.md` and `DOCS.md` are in the addon folder (`skolaonline_caldav_sync/`), not the repo root.

### Dockerfile constraints
- Base image: `FROM ghcr.io/home-assistant/base:latest` — do NOT use `python:*` or `alpine:*`.
- Entry point: `COPY run.sh /` + `RUN chmod a+x /run.sh` + `CMD ["/run.sh"]` — this is the HA-required pattern.
- Source files go to `/app/` via `COPY --chmod=755 src/ /app/`.
- Use `py3-lxml` from apk (pre-built) rather than installing `lxml` via pip to avoid Alpine build failures on `aarch64`.
- Do NOT use a custom `apparmor.txt` — HA's default AppArmor profile is sufficient.
- Do NOT set a custom `ENTRYPOINT` — use `CMD` only.

### Version bumping
- Bump the version in `config.yaml` for any change that requires reinstalling the addon in HA (code changes, Dockerfile changes, new config options).
- Documentation-only changes (README, DOCS.md, CHANGELOG.md, translations) do NOT require a version bump.

### SkolaOnline integration (`skolaonline.py`)
- The marketing site is at `www.skolaonline.cz`; the actual application is at `aplikace.skolaonline.cz`.
- Login is a plain POST to `https://aplikace.skolaonline.cz/SOL/Prihlaseni.aspx` with fields `JmenoUzivatele`, `HesloUzivatele`, and `btnLogin`. No hidden ViewState/CSRF tokens are needed.
- Login failure is detected by the Czech error text "Neplatné uživatelské jméno nebo heslo" in the response, or by "Prihlaseni" still appearing in the response URL.
- The homework list page (`KUK005_UkolyStudenta.aspx`) uses an Infragistics WebGrid paginated at 25 rows/page. Total record count is in `span.UWGPagerText`. Page navigation uses ASP.NET postback: `__EVENTTARGET=ctl00$main$wg`, `__EVENTARGUMENT=Page:<N>`.
- The "show completed" filter is a checkbox (`ctl00$main$cbZobrazitSplneneOdevzdane`) that requires an ASP.NET postback to activate. Always send it to get all assignments.
- Homework table column layout (0-indexed): `ORGANIZACE_ID | OBDOBI_ID | UKOL_OSOBA_ID | UKOL_ID | OSOBA_ID | DETAIL | NAZEV_UKOLU | PREDMET | TERMIN_PRIDELENI | TERMIN_ODEVZDANI_TEXT | ODEVZDANO_TEXT`. `UKOL_OSOBA_ID` (col 2) is used only for data-row detection (GUID check); `UKOL_ID` (col 3) is the stable assignment ID used everywhere else.
- Detail page (`KUK006_OdevzdaniUkolu.aspx?UkolID=<UKOL_ID>`) has a 2-cell `<tr>` where col 0 = "Podrobné zadání:" and col 1 = description content. Match only 2-cell rows to avoid catching the outer wrapper row.
- Descriptions are fetched lazily (only for new assignments) to avoid 100+ HTTP requests per sync cycle.

### iCloud Reminders (`icloud_reminders.py`)
- Uses `caldav` Python library. Auth: Basic Auth with Apple ID + **app-specific password** (NOT the Apple ID password). iCloud requires 2FA so regular passwords are rejected.
- Service discovery via `client.principal()` → list calendars → filter by VTODO component support.
- Family shared reminder lists appear as regular VTODO-capable calendars in the principal's home; find by display name (case-insensitive).
- Creating a list: `cal_home.make_calendar(name=..., supported_calendar_component_set=["VTODO"])`.
- Use `DUE;VALUE=DATE:YYYYMMDD` (date-only, no time) to avoid timezone-shift issues.
- `_escape_ical()` handles `\xa0` (non-breaking space common in Czech web content), backslashes, semicolons, and commas.
- iCloud maintains a GLOBAL UID index across ALL calendars. Use random UUID4 for VTODO UIDs; store logical→icloud UUID map in `/data/icloud_uid_map.json`. Retry with a fresh UUID4 on 412 (conflict).

### Generic CalDAV (`generic_caldav.py`)
- Works with any standard CalDAV server (Nextcloud, Radicale, Baikal, etc.).
- Uses logical UIDs directly — no UUID remapping needed.
- Auth: Basic Auth with `caldav_url`, `caldav_username`, `caldav_password` from config.

