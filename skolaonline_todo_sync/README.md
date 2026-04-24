# SkolaOnline CalDAV Sync

Scrapes homework assignments from [SkolaOnline.cz](https://www.skolaonline.cz) (Czech school parent portal) and syncs them as reminders to a **CalDAV calendar** — iCloud Reminders or any standard CalDAV server (Nextcloud, Radicale, Baikal, etc.).

## Features

- Authenticates to SkolaOnline as a parent
- Supports multiple pupils — each can have its own reminder list and sync strategy
- Two sync strategies: `single` (one item per assignment) or `parse_du` (parses individual DÚ lines from the assignment description)
- Deduplicates — existing reminders are never re-created
- Configurable sync interval
- Optional `name_prefix` per pupil (e.g. `[Maxim]`) when two pupils share one list
- Works with iCloud Reminders or any CalDAV server

## Installation

1. In Home Assistant go to **Settings → Add-ons → Add-on Store**
2. Click ⋮ → **Repositories** and add `https://github.com/hovorkap/sol-sync`
3. Find and install **SkolaOnline CalDAV Sync**
4. Configure and start the add-on

## Configuration

### SkolaOnline credentials

| Option | Description |
|--------|-------------|
| `skolaonline_username` | SkolaOnline parent login (email) |
| `skolaonline_password` | SkolaOnline password |

### Calendar backend (`cal_backend`)

Select `icloud` (default) or `caldav`.

#### iCloud Reminders (`cal_backend: icloud`)

| Option | Description |
|--------|-------------|
| `icloud_apple_id` | Apple ID (email) |
| `icloud_app_password` | App-specific password from [appleid.apple.com](https://appleid.apple.com) → Security → App-Specific Passwords — **not** your regular Apple ID password |

#### Generic CalDAV (`cal_backend: caldav`)

| Option | Description |
|--------|-------------|
| `caldav_url` | CalDAV server root URL, e.g. `https://nextcloud.example.com/remote.php/dav` |
| `caldav_username` | CalDAV username |
| `caldav_password` | CalDAV password |

### General options

| Option | Default | Description |
|--------|---------|-------------|
| `sync_interval` | `30` | Minutes between syncs |
| `default_list_name` | `Homework` | Reminder list / calendar name (can be overridden per pupil) |

### Per-pupil options (`pupils` list)

| Option | Description | Default |
|--------|-------------|---------|
| `sol_name` | Pupil name as shown in SkolaOnline dropdown (surname first, e.g. `Novak Jan`) | _(required)_ |
| `strategy` | `single` or `parse_du` | `single` |
| `list_name` | Reminder list name for this pupil; falls back to `default_list_name` if empty | _(empty)_ |
| `name_prefix` | If set, prepends `[prefix] ` to every reminder title | _(empty)_ |
| `include_past` | Include assignments with a past due date | `false` |

### Example configuration

```yaml
skolaonline_username: parent@example.com
skolaonline_password: secret
cal_backend: icloud
icloud_apple_id: parent@example.com
icloud_app_password: xxxx-xxxx-xxxx-xxxx
sync_interval: 60
default_list_name: Homework
pupils:
  - sol_name: "Novak Jan"
    strategy: parse_du
    list_name: ""
    name_prefix: ""
    include_past: false
```

## iCloud Reminders setup

1. Generate an **app-specific password** at [appleid.apple.com](https://appleid.apple.com) → Security → App-Specific Passwords
2. Fill in `icloud_apple_id` and `icloud_app_password` in the add-on configuration
3. On your iPhone go to **Settings → Reminders → Accounts → Add Account → Other → Add CalDAV Account**
   - Server: `https://caldav.icloud.com`
   - Username: your Apple ID
   - Password: the app-specific password
4. The CalDAV-backed lists will appear in Reminders — the add-on writes into these lists

