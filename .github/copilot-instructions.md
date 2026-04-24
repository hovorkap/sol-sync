# Copilot Instructions – SkolaOnline ToDo Sync

## Project overview

Home Assistant addon that synchronizes homework assignments from **SkolaOnline.cz** (Czech school parent portal) to **Microsoft To Do** via the Microsoft Graph API.

This is a **GitHub add-on repository** for Home Assistant. Users add the repo URL to HA and install the addon from there.

## Repository layout

```
repository.yaml                    # HA add-on repository metadata
README.md
CHANGELOG.md
skolaonline_todo_sync/
  config.yaml                      # HA addon manifest (name, slug, options, schema, arch)
  Dockerfile                       # FROM $BUILD_FROM (HA base image), alpine + Python
  run.sh                           # #!/usr/bin/with-contenv bashio entry point
  apparmor.txt                     # AppArmor policy (outbound HTTPS only)
  src/
    main.py                        # Reads HA options via bashio, runs sync loop
    skolaonline.py                 # SkolaOnline HTTP/scraping client (complete)
    icloud_reminders.py            # iCloud Reminders CalDAV client (primary backend)
    microsoft_todo.py              # Microsoft Graph API client (secondary backend)
    sync.py                        # Homework → reminder mapping, strategy logic
    requirements.txt
```

## Architecture

**Data flow:** `main.py` reads config → `SkolaOnlineClient.login()` → `SkolaOnlineClient.get_homework()` → `sync_homework()` → backend `create_task()`.

**Auth:**
- SkolaOnline: HTTP session with plain POST login (no ViewState)
- iCloud: CalDAV Basic Auth with Apple ID + app-specific password (from appleid.apple.com)
- Microsoft To Do: MSAL device-code flow (delegated, `Tasks.ReadWrite`). Tokens in `/data/ms_token_cache.json`.

**Backend selection:** `sync_backend` config option. `icloud` uses `icloud_reminders.ICloudRemindersClient` (CalDAV/VTODO). `microsoft` uses `microsoft_todo.MicrosoftToDoClient` (Graph API). Both expose the same interface: `get_or_create_list()`, `get_task_uids()` / `get_tasks()`, `create_task()`.

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
    list_name: "Maxim Homework" # reminder list / calendar name
    name_prefix: "Maxim"        # if non-empty, prefix all titles with "[Maxim] "
```
`name_prefix` is an explicit string (not derived). Use it when two pupils share the same `list_name` to distinguish their items.

**UID scoping:** UIDs include `osoba_id` (the pupil's person ID from col 4) to prevent collisions:
- `single`: `SO-{osoba_id}-{ukol_id}`
- `parse_du`: `SO-{osoba_id}-{ukol_id}-du-{sha1_hash}`

**Polling loop:** `main.py` sleeps 1 second at a time in a `while _running` loop and checks a `_running` flag set by `SIGTERM`. Do not replace with `time.sleep(interval)`.

## Key conventions

### Home Assistant addon constraints
- Configuration is read with `bashio.config("key")` — not env vars or argparse.
- Persistent state (tokens, checkpoints) goes in `/data/`. This directory survives addon restarts.
- Log to stdout/stderr only. Use Python `logging` — never write to log files.
- `run.sh` uses `#!/usr/bin/with-contenv bashio` (not plain bash) to inherit s6 environment variables.
- When adding new user-facing config options, update both `options:` and `schema:` in `config.yaml`.

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

### Microsoft To Do (`microsoft_todo.py`)
- All Graph requests go through `_get_token()` which silently refreshes via MSAL — do not cache the token string yourself.
- Always call `_save_cache()` after acquiring a token to persist refresh tokens.

### Docker / build
- Use `py3-lxml` from apk (pre-built) rather than installing `lxml` via pip to avoid Alpine build failures on `aarch64`.
- Only declare architectures in `config.yaml` that have been tested with a real build.

## What needs implementation

The remaining work:
1. **iCloud auth testing** — test against a real iCloud account; iCloud CalDAV has known quirks. Adjust `icloud_reminders.py` as needed.
2. **Microsoft To Do auth** (if using `microsoft` backend) — device-code flow needs a one-time interactive login
3. **HA integration testing** — validate `bashio` config reading and Docker build in a real HA environment
