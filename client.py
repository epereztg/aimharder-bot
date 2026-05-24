import hashlib
from datetime import datetime
from typing import Union

from requests import Session

LOGIN_URL = "https://aimharder.com/api/login"


class AimHarderClient:
    def __init__(self, email: str, password: str, box_name: str, box_id: int):
        self.box_name = box_name
        self.box_id = box_id
        self.session = self._login(email, password)

    def _base_url(self) -> str:
        return f"https://{self.box_name}.aimharder.com"

    def _date_str(self, date: datetime) -> str:
        return date.strftime("%Y%m%d")

    def _generate_fingerprint(self, email: str) -> str:
        return hashlib.sha256(f"aimharder-bot-{email}".encode()).hexdigest()[:50]

    def _login(self, email: str, password: str) -> Session:
        session = Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # ⚠️ NO ponemos Content-Type aquí — cada request lo gestiona solo
            "Origin": "https://aimharder.com",
            "Referer": "https://aimharder.com/login",
        })
        response = session.post(
            LOGIN_URL,
            json={  # json= pone automáticamente Content-Type: application/json
                "username": email,
                "password": password,
                "fingerprint": self._generate_fingerprint(email),
            },
        )
        response.raise_for_status()
        data = response.json()
        auth = data.get("data", {}).get("auth", {})
        if not auth.get("authOK"):
            raise RuntimeError(f"Login failed: {data}")
        print("Logged successfully")
        return session

    def list_classes(self, date: datetime) -> list[dict]:
        url = f"{self._base_url()}/api/bookings"
        resp = self.session.get(url, params={"box": self.box_id, "day": self._date_str(date)})
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("bookings", data.get("classes", []))
        return []

    def book_class(self, class_id: Union[int, str], date: datetime, insist: int = 0) -> dict:
        url = f"{self._base_url()}/api/book"
        resp = self.session.post(
            url,
            data={"id": str(class_id), "day": self._date_str(date), "insist": insist},
            # data= pone automáticamente Content-Type: application/x-www-form-urlencoded
        )
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    def logout(self):
        try:
            self.session.get(f"{self._base_url()}/logout", allow_redirects=True, timeout=10)
        except Exception:
            pass
        self.session.cookies.clear()
