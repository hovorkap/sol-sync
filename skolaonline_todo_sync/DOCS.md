# SkolaOnline Sync

Doplněk synchronizuje domácí úkoly ze [SkolaOnline.cz](https://www.skolaonline.cz) do CalDAV kalendáře (iCloud Připomínky nebo jiný CalDAV server).

## Konfigurace

### SkolaOnline

| Parametr | Popis |
|---|---|
| `skolaonline_username` | Přihlašovací jméno do SkolaOnline |
| `skolaonline_password` | Heslo do SkolaOnline |

### Typ kalendáře (`cal_backend`)

- **`icloud`** – iCloud Připomínky (CalDAV na caldav.icloud.com)
- **`caldav`** – Libovolný CalDAV server (Nextcloud, Radicale, Baikal apod.)

#### iCloud (`cal_backend: icloud`)

| Parametr | Popis |
|---|---|
| `icloud_apple_id` | Vaše Apple ID (e-mail) |
| `icloud_app_password` | Heslo pro konkrétní aplikaci z [appleid.apple.com](https://appleid.apple.com) → Zabezpečení → Hesla pro aplikace |

> **Důležité:** Použijte heslo pro konkrétní aplikaci, **ne** vaše běžné heslo Apple ID. Běžné heslo kvůli 2FA nefunguje.

#### Obecný CalDAV (`cal_backend: caldav`)

| Parametr | Popis |
|---|---|
| `caldav_url` | URL CalDAV serveru, např. `https://nextcloud.example.com/remote.php/dav` |
| `caldav_username` | Uživatelské jméno |
| `caldav_password` | Heslo |

### Obecná nastavení

| Parametr | Výchozí | Popis |
|---|---|---|
| `sync_interval` | `30` | Interval synchronizace v minutách |
| `default_list_name` | `Homework` | Výchozí název seznamu/kalendáře |

### Žáci (`pupils`)

Každý žák je samostatný záznam v seznamu:

| Parametr | Popis |
|---|---|
| `sol_name` | Jméno žáka přesně podle rozbalovacího menu SkolaOnline (příjmení + jméno) |
| `strategy` | `parse_du` – rozbalí skupinové úkoly na jednotlivé DÚ; `single` – jeden úkol za zadání |
| `list_name` | Název seznamu pro tohoto žáka (pokud není uvedeno, použije se `default_list_name`) |
| `name_prefix` | Předpona v závorce před názvem úkolu, např. `Maxim` → `[Maxim] Matematika DÚ 1` |
| `include_past` | Zahrnout i starší (splněné) úkoly |

## Poznámky k iCloud

Po první synchronizaci se záznamy v iCloud zobrazují v aplikaci Připomínky. Pokud se nezobrazují okamžitě v iOS aplikaci, přidejte CalDAV účet ručně: **Nastavení → Připomínky → Účty → Přidat účet → Jiný → Přidat CalDAV účet** (server: `caldav.icloud.com`).
