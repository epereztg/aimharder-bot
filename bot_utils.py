import os
import json
import requests
import pytz
from datetime import datetime
from typing import Optional

# --- Configuration ---
LOGIN_URL = "https://login.aimharder.com/"
TIMEZONE = "Europe/Madrid"

# Default box configuration — read from environment 
DEFAULT_BOX_NAME = os.environ.get("BOX_NAME", "")
DEFAULT_BOX_ID = int(os.environ.get("BOX_ID", 0))


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

