import os
import json
import requests
import pytz
from datetime import datetime
from typing import Optional

# --- Configuration ---
LOGIN_URL = "https://login.aimharder.com/"
TIMEZONE = "Europe/Madrid"

# Default box configuration
DEFAULT_BOX_NAME = "wezonearturosoria"
DEFAULT_BOX_ID = 10002

def login(email: str, password: str, session: requests.Session, box_name: str, box_id: int) -> bool:
    """
    Authenticate with AimHarder.
    Returns True if login is successful.
    """
    login_payload = {
        "login": "Log in",
        "mail": email,
        "pw": password,
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://login.aimharder.com",
        "Referer": "https://login.aimharder.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest", 
    }
    
    response = session.post(LOGIN_URL, data=login_payload, headers=headers, allow_redirects=True)
    
    if response.ok:
        if "Too many wrong attempts" in response.text:
            print("❌ Login failed: Too many wrong attempts")
            return False
        if "Incorrect credentials" in response.text or "Contraseña incorrecta" in response.text:
            print("❌ Login failed: Incorrect credentials")
            return False

        if box_name in response.url:
            print(f"✅ Login successful! Redirected to: {response.url}")
            return True
        
        if "PHPSESSID" in session.cookies.get_dict() or any("aim" in c.lower() for c in session.cookies.get_dict()):
            print("✅ Login successful (session cookie obtained)")
            return True
    
    print(f"❌ Login failed. Status: {response.status_code}")
    print(f"   Response URL: {response.url}")
    return False

def get_spanish_date_str(date_obj: datetime) -> str:
    """Format date as 'DD Mmm' (e.g. '19 Ene') for matching with AimHarder."""
    months = {
        1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
    }
    return f"{date_obj.day} {months[date_obj.month]}"

def get_full_spanish_date_str(date_obj: datetime) -> str:
    """Format date as 'LUNES 19 ENE' for display."""
    days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    months = {
        1: "ENE", 2: "FEB", 3: "MAR", 4: "ABR", 5: "MAY", 6: "JUN",
        7: "JUL", 8: "AGO", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DIC"
    }
    day_name = days[date_obj.weekday()].upper()
    return f"{day_name} {date_obj.day} {months[date_obj.month]}"

def send_telegram_notification(message: str) -> bool:
    """
    Send a notification via Telegram Bot API.
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("⚠️ Telegram configuration missing (TELEGRAM_TOKEN or TELEGRAM_CHAT_ID). Skipping notification.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        print(f"📡 Sending Telegram Notification...")
        response = requests.post(url, json=payload, timeout=10)
        return response.ok
    except Exception as e:
        print(f"⚠️ Failed to send Telegram notification: {e}")
        return False

def fetch_wod(session: requests.Session, box_name: str, target_date: datetime) -> Optional[str]:
    """
    Fetch the WOD for the target date from the main dashboard context.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("⚠️ BeautifulSoup not found. Cannot fetch WOD.")
        return None

    url = f"https://{box_name}.aimharder.com/"
    print(f"🔄 Fetching WOD from {url}...")
    
    response = session.get(url)
    if not response.ok:
        return None

    import re
    user_id_match = re.search(r"userID:\s*(\d+)", response.text)
    if not user_id_match:
        return None
    
    user_id = user_id_match.group(1)
    
    activity_url = f"https://{box_name}.aimharder.com/api/activity"
    params = {
        "timeLineFormat": 0,
        "timeLineContent": 7,
        "userID": user_id
    }
    
    act_response = session.get(activity_url, params=params)
    if not act_response.ok:
        return None
        
    try:
        data = act_response.json()
    except:
        return None

    target_date_str = get_spanish_date_str(target_date)
    
    if "elements" not in data:
        return None
        
    wods_found = []
    for element in data.get("elements", []):
        if element.get("day") == target_date_str:
            wod_class = element.get("wodClass", "General")
            print(f"      ✨ Found WOD for {target_date_str}: {wod_class}")
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
