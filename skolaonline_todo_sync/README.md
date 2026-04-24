# SkolaOnline ToDo Sync

Scrapes homework assignments from [SkolaOnline.cz](https://www.skolaonline.cz) (Czech school parent portal) and syncs them as reminders to **iCloud Reminders** via CalDAV.

## Features

- Authenticates to SkolaOnline as a parent
- Supports multiple pupils — each can have its own reminder list and sync strategy
- Two sync strategies: `single` (one item per assignment) or `parse_du` (parses individual DÚ lines from the assignment description)
- Deduplicates — existing reminders are never re-created
- Configurable sync interval
- Optional `name_prefix` per pupil (e.g. `[Maxim]`) when two pupils share one list

## Installation

1. In Home Assistant go to **Settings → Add-ons → Add-on Store**
2. Click ⋮ → **Repositories** and add `https://github.com/hovorkap/sol-sync`
3. Find and install **SkolaOnline ToDo Sync**
4. Configure and start the add-on

## Configuration

### Top-level options

| Option | Description | Default |
|--------|-------------|---------|
| `skolaonline_username` | SkolaOnline parent login (email) | _(required)_ |
| `skolaonline_password` | SkolaOnline password | _(required)_ |
| `icloud_apple_id` | Apple ID (email) | _(required)_ |
| `icloud_app_password` | App-specific password from [appleid.apple.com](https://appleid.apple.com) | _(required)_ |
| `sync_interval` | Minutes between syncs | `30` |

### Per-pupil options (`pupils` list)

| Option | Description | Default |
|--------|-------------|---------|
| `sol_name` | Pupil name as shown in SkolaOnline dropdown (surname first, e.g. `Hovorka Maxim`) | _(required)_ |
| `strategy` | `single` or `parse_du` | `single` |
| `list_name` | Reminder list name to sync into | `Homework` |
| `name_prefix` | If set, prepends `[prefix] ` to every reminder title | _(empty)_ |
| `include_past` | Include assignments with a past due date | `false` |

### Example configuration

```yaml
skolaonline_username: parent@example.com
skolaonline_password: secret
icloud_apple_id: parent@example.com
icloud_app_password: xxxx-xxxx-xxxx-xxxx
sync_interval: 60
pupils:
  - sol_name: "Hovorka Maxim"
    strategy: parse_du
    list_name: Homework
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

