"""
SkolaOnline client.

Authentication:
  - Login form is served at https://www.skolaonline.cz/prihlaseni/
  - The form POSTs credentials directly to:
      https://aplikace.skolaonline.cz/SOL/Prihlaseni.aspx
  - No hidden ASP.NET ViewState tokens are required for login.
  - On success the server issues session cookies and redirects into the app.
  - On failure the response URL still contains "Prihlaseni".

App base URL: https://aplikace.skolaonline.cz/SOL/App/
Known pages:
  - Prihlaseni.aspx                     – login
  - App/Spolecne/KZZ010_RychlyPrehled   – dashboard (post-login landing)
  - App/Ukoly/KUK005_UkolyStudenta      – homework list
  - App/Ukoly/KUK006_OdevzdaniUkolu     – homework detail (?UkolID=<ukol_osoba_id>)

Homework table column layout (0-indexed):
  0  ORGANIZACE_ID    (hidden)
  1  OBDOBI_ID        (hidden)
  2  UKOL_OSOBA_ID    (hidden) ← GUID presence check for data row detection
  3  UKOL_ID          (hidden) ← stable assignment id; used in detail URL as UkolID=
  4  OSOBA_ID         (hidden) ← pupil's person ID; used to scope UIDs in shared lists
  5  DETAIL           (link column)
  6  NAZEV_UKOLU      title
  7  PREDMET          subject
  8  TERMIN_PRIDELENI assigned datetime
  9  TERMIN_ODEVZDANI_TEXT due date  (format: d.m.yyyy HH:MM, no leading zeros)
  10 ODEVZDANO_TEXT   status ("odevzdáno" = completed)

Pupil selection:
  The homework page has a Žák (pupil) dropdown:
    name:  ctl00$listOfChildrenPart$listOfChildren$DDLChildren
    value: <ORG_ID>#<OSOBA_ID>  (e.g. "C1057#C3449720")
    text:  "Příjmení Jméno"  (Czech surname-first format)

  Selecting a pupil triggers an ASP.NET postback that reloads the list
  filtered for that pupil. Always do a fresh GET before each pupil's sync.
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

APP_BASE = "https://aplikace.skolaonline.cz/SOL"
LOGIN_URL = f"{APP_BASE}/Prihlaseni.aspx"
HOMEWORK_URL = f"{APP_BASE}/App/Ukoly/KUK005_UkolyStudenta.aspx"
HOMEWORK_DETAIL_URL = f"{APP_BASE}/App/Ukoly/KUK006_OdevzdaniUkolu.aspx"
_PUPIL_DROPDOWN = "ctl00$listOfChildrenPart$listOfChildren$DDLChildren"

_LOGIN_ERROR_TEXT = "Neplatné uživatelské jméno nebo heslo"
# Column indexes in the homework data table (see module docstring for full layout)
_COL_UKOL_OSOBA_ID = 2  # used only for GUID presence check
_COL_UKOL_ID = 3        # stable assignment ID; used in detail URL as UkolID=
_COL_OSOBA_ID = 4       # pupil's person ID; used to scope UIDs in shared lists
_COL_TITLE = 6
_COL_SUBJECT = 7
_COL_DUE = 9
_COL_STATUS = 10
_COMPLETED_STATUS = "odevzdáno"


@dataclass
class Pupil:
    """A pupil available in the SkolaOnline pupil dropdown."""
    display_name: str   # as shown in the dropdown (Czech surname-first)
    value: str          # dropdown option value (e.g. "C1057#C3449720")


@dataclass
class HomeworkAssignment:
    id: str               # UKOL_ID – used in the detail URL as UkolID=; stable deduplication key
    osoba_id: str         # OSOBA_ID – pupil's person ID; used to scope UIDs in shared lists
    subject: str
    title: str
    description: str      # "Podrobné zadání" from the detail page; empty until fetched
    due_date: Optional[date]
    is_completed: bool


class SkolaOnlineClient:
    """Authenticated HTTP session client for SkolaOnline."""

    def __init__(self, username: str, password: str):
        self._username = username
        self._password = password
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; SkolaOnlineToDoSync/0.1)",
            "Referer": "https://www.skolaonline.cz/prihlaseni/",
        })
        self._logged_in = False

    def login(self) -> None:
        """
        Establish an authenticated session with SkolaOnline.

        POSTs credentials to Prihlaseni.aspx. On success the server redirects
        into the app and sets session cookies on the aplikace.skolaonline.cz domain.
        Raises RuntimeError on authentication failure.
        """
        log.info("Logging in to SkolaOnline as %s...", self._username)

        payload = {
            "JmenoUzivatele": self._username,
            "HesloUzivatele": self._password,
            "btnLogin": "Přihlásit do aplikace",
        }

        response = self._session.post(LOGIN_URL, data=payload, timeout=30)
        response.raise_for_status()

        if _LOGIN_ERROR_TEXT in response.text:
            raise RuntimeError(
                "SkolaOnline login failed: invalid credentials or account locked"
            )

        if "Prihlaseni" in response.url and "JmenoUzivatele" in response.text:
            raise RuntimeError(
                f"SkolaOnline login failed: unexpected redirect to {response.url}"
            )

        self._logged_in = True
        log.info("Logged in to SkolaOnline. Session landing URL: %s", response.url)

    def get_pupils(self) -> list[Pupil]:
        """
        Return the list of pupils available in the Žák dropdown.

        Fetches the homework page and parses the pupil dropdown. The returned
        list may contain multiple entries; display names are in Czech surname-first
        format (e.g. "Hovorka Maxim").
        """
        if not self._logged_in:
            self.login()
        resp = self._session.get(HOMEWORK_URL + "?reset=true", timeout=30)
        resp.raise_for_status()
        return _parse_pupils(BeautifulSoup(resp.text, "lxml"))

    def get_homework(self, pupil_value: Optional[str] = None) -> list[HomeworkAssignment]:
        """
        Retrieve all homework assignments (including completed ones).

        If pupil_value is provided (a dropdown option value from get_pupils()),
        the homework list is filtered to that pupil before scraping.

        Returns assignments without descriptions for performance — descriptions
        are fetched lazily via get_assignment_description() only for new items.
        """
        if not self._logged_in:
            self.login()
        return self._scrape_homework(pupil_value=pupil_value)

    def get_assignment_description(self, ukol_id: str) -> str:
        """
        Fetch the full description ("Podrobné zadání") for a single assignment.

        Only call this for new assignments not yet synced to avoid fetching
        descriptions for the entire history on every sync.
        """
        if not self._logged_in:
            self.login()

        resp = self._session.get(
            HOMEWORK_DETAIL_URL,
            params={"UkolID": ukol_id},
            timeout=30,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        # The detail page has a 2-cell table row: <td>Podrobné zadání:</td><td>{content}</td>
        # Match only the label row (not an outer row that incidentally contains the text).
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if (
                len(cells) == 2
                and cells[0].get_text(strip=True).rstrip(":") == "Podrobné zadání"
            ):
                return cells[1].get_text(separator="\n", strip=True)
        return ""

    def _scrape_homework(self, pupil_value: Optional[str] = None) -> list[HomeworkAssignment]:
        """
        Scrape the homework list page, including completed/cancelled items.

        For each pupil sync, starts with a fresh GET to avoid stale ASP.NET page
        state from previous requests. If pupil_value is given, fires a pupil-selection
        postback first, then the "show completed" postback, then paginates.
        """
        resp = self._session.get(HOMEWORK_URL + "?reset=true", timeout=30)
        resp.raise_for_status()

        if "Prihlaseni" in resp.url:
            self._logged_in = False
            raise RuntimeError("SkolaOnline session expired, please restart the addon.")

        soup = BeautifulSoup(resp.text, "lxml")

        if pupil_value is not None:
            soup = self._select_pupil(soup, pupil_value)

        soup = self._postback_show_all(soup)

        # Determine total page count from the pager
        total_pages = self._get_page_count(soup)
        log.debug("Homework list has %d page(s).", total_pages)

        all_assignments = self._parse_homework_table(soup)

        for page in range(2, total_pages + 1):
            soup_page = self._navigate_to_page(soup, page)
            all_assignments.extend(self._parse_homework_table(soup_page))
            soup = soup_page  # update for next page's __EVENTVALIDATION

        log.info("Found %d homework assignments across %d page(s).", len(all_assignments), total_pages)
        return all_assignments

    def _select_pupil(self, soup: BeautifulSoup, pupil_value: str) -> BeautifulSoup:
        """Select a pupil via ASP.NET postback and return the reloaded page soup."""
        def _hidden(name: str) -> str:
            el = soup.find("input", {"name": name})
            return el["value"] if el and el.get("value") else ""

        postback_data = {
            "__EVENTTARGET": _PUPIL_DROPDOWN,
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE_SESSION_KEY": _hidden("__VIEWSTATE_SESSION_KEY"),
            "__VIEWSTATE": "",
            "__EVENTVALIDATION": _hidden("__EVENTVALIDATION"),
            _PUPIL_DROPDOWN: pupil_value,
            "ctl00xmainxwg": "",
        }

        resp = self._session.post(HOMEWORK_URL + "?reset=true", data=postback_data, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def _postback_show_all(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Submit the 'show completed' checkbox postback and return the resulting page."""
        def _hidden(name: str) -> str:
            el = soup.find("input", {"name": name})
            return el["value"] if el and el.get("value") else ""

        postback_data = {
            "__EVENTTARGET": "ctl00$main$cbZobrazitSplneneOdevzdane",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE_SESSION_KEY": _hidden("__VIEWSTATE_SESSION_KEY"),
            "__VIEWSTATE": "",
            "__EVENTVALIDATION": _hidden("__EVENTVALIDATION"),
            "ctl00$main$cbZobrazitSplneneOdevzdane": "on",
            "ctl00xmainxwg": "",
        }

        resp = self._session.post(HOMEWORK_URL + "?reset=true", data=postback_data, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def _navigate_to_page(self, current_soup: BeautifulSoup, page: int) -> BeautifulSoup:
        """Navigate the grid to the given page number via ASP.NET postback."""
        def _hidden(name: str) -> str:
            el = current_soup.find("input", {"name": name})
            return el["value"] if el and el.get("value") else ""

        postback_data = {
            "__EVENTTARGET": "ctl00$main$wg",
            "__EVENTARGUMENT": f"Page:{page}",
            "__LASTFOCUS": "",
            "__VIEWSTATE_SESSION_KEY": _hidden("__VIEWSTATE_SESSION_KEY"),
            "__VIEWSTATE": "",
            "__EVENTVALIDATION": _hidden("__EVENTVALIDATION"),
            "ctl00$main$cbZobrazitSplneneOdevzdane": "on",
            "ctl00xmainxwg": "",
        }

        resp = self._session.post(HOMEWORK_URL + "?reset=true", data=postback_data, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    @staticmethod
    def _get_page_count(soup: BeautifulSoup) -> int:
        """Return the total number of grid pages from the pager area."""
        pager = soup.find("td", class_="igtbl_PagerArea")
        if not pager:
            return 1
        page_links = pager.find_all("a", class_="igtbl_PageLink")
        current = pager.find("span", class_="igtbl_PageCurrent")
        all_pages = [current] + page_links if current else page_links
        nums = []
        for el in all_pages:
            try:
                nums.append(int(el.get_text(strip=True)))
            except ValueError:
                pass
        return max(nums) if nums else 1

    def _parse_homework_table(self, soup: BeautifulSoup) -> list[HomeworkAssignment]:
        """
        Parse the homework data table.

        Identifies the table by its header row containing 'Název úkolu'.
        Data rows have 11 cells; the column layout is documented in the module docstring.
        """
        homework_table = None
        for table in soup.find_all("table"):
            header_text = table.get_text()
            if "Název úkolu" in header_text and "Termín odevzdání" in header_text:
                homework_table = table
                break

        if homework_table is None:
            log.warning("Homework table not found on page.")
            return []

        assignments: list[HomeworkAssignment] = []
        rows = homework_table.find_all("tr")

        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 11:
                continue  # header or malformed row

            ukol_osoba_id = cells[_COL_UKOL_OSOBA_ID]
            # Skip rows that don't look like data (e.g. header rendered as <td>)
            if not _looks_like_guid(ukol_osoba_id):
                continue

            assignments.append(HomeworkAssignment(
                id=cells[_COL_UKOL_ID],
                osoba_id=cells[_COL_OSOBA_ID],
                subject=cells[_COL_SUBJECT],
                title=cells[_COL_TITLE],
                description="",  # fetched lazily via get_assignment_description()
                due_date=_parse_due_date(cells[_COL_DUE]),
                is_completed=_COMPLETED_STATUS in cells[_COL_STATUS].lower(),
            ))

        log.info("Found %d homework assignments.", len(assignments))
        return assignments


def _looks_like_guid(value: str) -> bool:
    """Return True if the value looks like a UUID/GUID (e.g. 'a1b2c3d4-...')."""
    parts = value.split("-")
    return len(parts) == 5 and all(p.isalnum() for p in parts)


def _parse_pupils(soup: BeautifulSoup) -> list[Pupil]:
    """Parse the Žák dropdown and return all available pupils."""
    select = soup.find("select", {"name": _PUPIL_DROPDOWN})
    if not select:
        return []
    pupils = []
    for option in select.find_all("option"):
        value = option.get("value", "").strip()
        name = " ".join(option.get_text().split())  # normalize whitespace
        if value and name:
            pupils.append(Pupil(display_name=name, value=value))
    return pupils


def _parse_due_date(text: str) -> Optional[date]:
    """
    Parse a Czech due date string into a date object.

    Expected formats (no leading zeros): 'd.m.yyyy HH:MM' or 'd.m.yyyy'
    """
    text = text.strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    log.debug("Could not parse due date: %r", text)
    return None
