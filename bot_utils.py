import os
import json
import requests


# --- Configuration ---
LOGIN_URL = "https://login.aimharder.com/"
TIMEZONE = "Europe/Madrid"

# Default box configuration — read from environment 
DEFAULT_BOX_NAME = os.environ.get("BOX_NAME", "")
DEFAULT_BOX_ID = int(os.environ.get("BOX_ID", 0))



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

