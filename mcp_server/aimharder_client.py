"""
aimharder_client.py
Low-level client for the AimHarder REST API.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LOGIN_URL = "https://login.aimharder.com/"
TIMEZONE = "Europe/Madrid"


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def login(
    email: str,
    password: str,
    box_name: str,
    box_id: int,
    session: Optional[requests.Session] = None,
) -> requests.Session:
    """
    Authenticate with AimHarder and return an authenticated session.

    Raises RuntimeError if authentication fails.
    """
    if session is None:
        session = requests.Session()

    payload = {
        "login": "Log in",
        "mail": email,
        "pw": password,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": LOGIN_URL.rstrip("/"),
        "Referer": LOGIN_URL,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }

    resp = session.post(LOGIN_URL, data=payload, headers=headers, allow_redirects=True)

    if not resp.ok:
        raise RuntimeError(f"Login HTTP error {resp.status_code}")

    text = resp.text
    if "Too many wrong attempts" in text:
        raise RuntimeError("Login failed: too many wrong attempts")
    if "Incorrect credentials" in text or "Contraseña incorrecta" in text:
        raise RuntimeError("Login failed: incorrect credentials")

    # AimHarder redirects to the box subdomain after successful login
    if box_name in resp.url:
        return session
    cookies = session.cookies.get_dict()
    if "PHPSESSID" in cookies or any("aim" in c.lower() for c in cookies):
        return session

    raise RuntimeError(f"Login failed. Final URL: {resp.url}")


# ---------------------------------------------------------------------------
# Classes / bookings
# ---------------------------------------------------------------------------

def _base_url(box_name: str) -> str:
    return f"https://{box_name}.aimharder.com"


def _date_str(date: datetime) -> str:
    return date.strftime("%Y%m%d")


def list_classes(
    session: requests.Session,
    date: datetime,
    box_name: str,
    box_id: int,
) -> list[dict]:
    """
    Return all classes available on *date*.

    Each item contains at least:
        id, className, timeid (e.g. "0700_60"), spots, bookedSpots, booked
    """
    url = f"{_base_url(box_name)}/api/bookings"
    params = {"box": box_id, "day": _date_str(date)}
    headers = {"Accept": "application/json", "Referer": _base_url(box_name)}

    resp = session.get(url, params=params, headers=headers)
    if not resp.ok:
        raise RuntimeError(f"list_classes HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"list_classes: invalid JSON – {exc}") from exc

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("bookings", data.get("classes", data.get("sessions", [])))
    return []


def book_class(
    session: requests.Session,
    class_id: int | str,
    date: datetime,
    box_name: str,
    box_id: int,
    insist: int = 0,
) -> dict:
    """
    Book a class by its *class_id* for the given *date*.

    Returns the raw JSON response dict from AimHarder, which contains:
        bookState  (1 = confirmed, other values = failure / waitlist)
        errorMssg  (human-readable reason on failure)
    """
    url = f"{_base_url(box_name)}/api/book"
    payload = {
        "id": str(class_id),
        "day": _date_str(date),
        "insist": insist,
        "familyId": "",
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "Referer": _base_url(box_name),
    }

    resp = session.post(url, data=payload, headers=headers)
    if not resp.ok:
        raise RuntimeError(f"book_class HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        return resp.json()
    except json.JSONDecodeError:
        return {"raw": resp.text}


def cancel_booking(
    session: requests.Session,
    class_id: int | str,
    date: datetime,
    box_name: str,
    box_id: int,
) -> dict:
    """
    Cancel an existing booking.

    Returns the raw JSON response dict from AimHarder.
    """
    url = f"{_base_url(box_name)}/api/book"
    payload = {
        "id": str(class_id),
        "day": _date_str(date),
        "insist": 0,
        "familyId": "",
        "delete": 1,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "Referer": _base_url(box_name),
    }

    resp = session.post(url, data=payload, headers=headers)
    if not resp.ok:
        raise RuntimeError(f"cancel_booking HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        return resp.json()
    except json.JSONDecodeError:
        return {"raw": resp.text}


def find_attendees(
    session: requests.Session,
    class_id: int | str,
    date: datetime,
    box_name: str,
    box_id: int,
) -> list[dict]:
    """
    Return the list of members booked into a specific class.

    Each item typically contains: id, name, surname, picture, …
    AimHarder exposes this via /api/bookings?bookingId=<id>&day=<date>.
    Falls back to filtering the full class list if the dedicated endpoint
    doesn't return the roster.
    """
    # First try the dedicated attendees endpoint
    url = f"{_base_url(box_name)}/api/bookings"
    params = {
        "box": box_id,
        "day": _date_str(date),
        "bookingId": str(class_id),
    }
    headers = {"Accept": "application/json", "Referer": _base_url(box_name)}

    resp = session.get(url, params=params, headers=headers)
    if resp.ok:
        try:
            data = resp.json()
            # The API may return {"bookings": [...members...]} when bookingId is set
            if isinstance(data, dict):
                # Look for a member/attendee list under various keys
                for key in ("bookings", "members", "attendees", "users", "people"):
                    val = data.get(key)
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        # Distinguish member lists from class lists by checking for 'name'
                        if "name" in val[0] or "surname" in val[0]:
                            return val
            # Sometimes the whole response IS the member list
            if isinstance(data, list) and data and "name" in data[0]:
                return data
        except json.JSONDecodeError:
            pass

    # Fallback: pull full class list and return the booked-users for this class
    classes = list_classes(session, date, box_name, box_id)
    for cls in classes:
        if str(cls.get("id", "")) == str(class_id):
            # AimHarder sometimes embeds `usersBooked` or `bookings`
            for key in ("usersBooked", "bookings", "members", "attendees"):
                attendees = cls.get(key)
                if isinstance(attendees, list):
                    return attendees
            break

    return []


def logout(
    session: requests.Session,
    box_name: str,
) -> None:
    """
    Log out by hitting the AimHarder logout endpoint and clearing session cookies.
    """
    try:
        session.get(
            f"{_base_url(box_name)}/logout",
            headers={"Referer": _base_url(box_name)},
            allow_redirects=True,
            timeout=10,
        )
    except Exception:
        pass
    session.cookies.clear()


def find_attendees_by_name(
    session: requests.Session,
    name_query: str,
    date: datetime,
    box_name: str,
    box_id: int,
) -> list[dict]:
    """
    Search across ALL classes on *date* and return attendees whose name
    contains *name_query* (case-insensitive).

    Returns a list of dicts, each with the attendee info plus
    a 'class_info' key indicating which class they are in.
    """
    classes = list_classes(session, date, box_name, box_id)
    results = []
    name_lower = name_query.lower()

    for cls in classes:
        class_id = cls.get("id")
        if class_id is None:
            continue

        attendees = find_attendees(session, class_id, date, box_name, box_id)
        for person in attendees:
            full_name = f"{person.get('name', '')} {person.get('surname', '')}".strip()
            if name_lower in full_name.lower():
                results.append({
                    **person,
                    "class_info": {
                        "id": class_id,
                        "name": cls.get("className", cls.get("name", "")),
                        "time": cls.get("timeid", cls.get("time", "")),
                    },
                })

    return results
