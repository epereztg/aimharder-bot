import json
import re
from datetime import datetime
from typing import Optional, Union

import requests

from exceptions import IncorrectCredentials, TooManyWrongAttempts, BookingFailed

LOGIN_URL = "https://login.aimharder.com/"

class AimHarderClient:
    def __init__(self, email: str, password: str, box_name: str, box_id: int):
        self.box_name = box_name
        self.box_id = box_id
        self.session = requests.Session()
        self._login(email, password)

    def _base_url(self) -> str:
        return f"https://{self.box_name}.aimharder.com"

    def _date_str(self, date: datetime) -> str:
        return date.strftime("%Y%m%d")

    def _login(self, email: str, password: str):
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

        resp = self.session.post(LOGIN_URL, data=payload, headers=headers, allow_redirects=True)

        if not resp.ok:
            raise RuntimeError(f"Login HTTP error {resp.status_code}")

        text = resp.text
        if "Too many wrong attempts" in text:
            raise TooManyWrongAttempts("Login failed: too many wrong attempts")
        if "Incorrect credentials" in text or "Contraseña incorrecta" in text:
            raise IncorrectCredentials("Login failed: incorrect credentials")

        if self.box_name in resp.url:
            return
            
        cookies = self.session.cookies.get_dict()
        if "PHPSESSID" in cookies or any("aim" in c.lower() for c in cookies):
            return

        raise RuntimeError(f"Login failed. Final URL: {resp.url}")

    def list_classes(self, date: datetime) -> list[dict]:
        url = f"{self._base_url()}/api/bookings"
        params = {"box": self.box_id, "day": self._date_str(date)}
        headers = {"Accept": "application/json", "Referer": self._base_url()}

        resp = self.session.get(url, params=params, headers=headers)
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

    def book_class(self, class_id: Union[int, str], date: datetime, insist: int = 0) -> dict:
        url = f"{self._base_url()}/api/book"
        payload = {
            "id": str(class_id),
            "day": self._date_str(date),
            "insist": insist,
            "familyId": "",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Referer": self._base_url(),
        }

        resp = self.session.post(url, data=payload, headers=headers)
        if not resp.ok:
            raise BookingFailed(f"book_class HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            return resp.json()
        except json.JSONDecodeError:
            return {"raw": resp.text}

    def cancel_booking(self, class_id: Union[int, str], date: datetime) -> dict:
        url = f"{self._base_url()}/api/book"
        payload = {
            "id": str(class_id),
            "day": self._date_str(date),
            "insist": 0,
            "familyId": "",
            "delete": 1,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Referer": self._base_url(),
        }

        resp = self.session.post(url, data=payload, headers=headers)
        if not resp.ok:
            raise RuntimeError(f"cancel_booking HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            return resp.json()
        except json.JSONDecodeError:
            return {"raw": resp.text}



    def logout(self):
        try:
            self.session.get(
                f"{self._base_url()}/logout",
                headers={"Referer": self._base_url()},
                allow_redirects=True,
                timeout=10,
            )
        except Exception:
            pass
        self.session.cookies.clear()

    def fetch_wod(self, target_date: datetime) -> Optional[str]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return None

        url = f"{self._base_url()}/"
        response = self.session.get(url)
        if not response.ok:
            return None

        user_id_match = re.search(r"userID:\s*(\d+)", response.text)
        if not user_id_match:
            return None
        
        user_id = user_id_match.group(1)
        
        activity_url = f"{self._base_url()}/api/activity"
        params = {
            "timeLineFormat": 0,
            "timeLineContent": 7,
            "userID": user_id
        }
        
        act_response = self.session.get(activity_url, params=params)
        if not act_response.ok:
            return None
            
        try:
            data = act_response.json()
        except Exception:
            return None

        # Spanish date string mapping
        months = {
            1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
            7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
        }
        target_date_str = f"{target_date.day} {months[target_date.month]}"
        
        if "elements" not in data:
            return None
            
        wods_found = []
        for element in data.get("elements", []):
            if element.get("day") == target_date_str:
                wod_class = element.get("wodClass", "General")
                notes_parts = []
                tipos = element.get("TIPOWODs", [])
                for tipo in tipos:
                    note_html = tipo.get("notes", "")
                    if note_html:
                        soup_note = BeautifulSoup(note_html, "html.parser")
                        text = soup_note.get_text(separator="\n")
                        notes_parts.append(text.strip())
                
                if notes_parts:
                    full_text = "\n\n".join(notes_parts)
                    wods_found.append(f"📌 {wod_class}:\n{full_text}")
        
        if not wods_found:
            return None
            
        return "\n\n".join(wods_found)
