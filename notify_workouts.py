#!/usr/bin/env python3
import argparse
import sys
import requests
from datetime import datetime, timedelta
import pytz
from bot_utils import (
    login, send_telegram_notification, get_spanish_date_str, 
    get_full_spanish_date_str,
    TIMEZONE, DEFAULT_BOX_NAME, DEFAULT_BOX_ID
)

def notify_all_workouts(session: requests.Session, box_name: str, days_ahead: int = 1) -> bool:
    """
    Fetch all workouts from the activity feed and send a single Telegram message for the next X days.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("⚠️ BeautifulSoup not found. Cannot fetch workouts.")
        return False

    url = f"https://{box_name}.aimharder.com/"
    print(f"🔄 Fetching all WODs from {url}...")
    
    response = session.get(url)
    if not response.ok:
        print(f"⚠️ Failed to fetch dashboard: {response.status_code}")
        return False

    import re
    user_id_match = re.search(r"userID:\s*(\d+)", response.text)
    if not user_id_match:
        print("⚠️ Could not find userID in dashboard HTML.")
        return False
    
    user_id = user_id_match.group(1)
    
    # Fetch Activity Feed (AJAX)
    activity_url = f"https://{box_name}.aimharder.com/api/activity"
    params = {
        "timeLineFormat": 0,
        "timeLineContent": 100, # Increased limit to ensure we get a full week across all user boxes
        "userID": user_id
    }
    
    act_response = session.get(activity_url, params=params)
    if not act_response.ok:
        print(f"⚠️ Failed to fetch activity: {act_response.status_code}")
        return False
        
    try:
        data = act_response.json()
    except Exception as e:
        print(f"⚠️ Failed to parse Activity JSON: {e}")
        return False

    if "elements" not in data:
        print("ℹ️ No 'elements' in activity feed.")
        return False
        
    wods_by_day = {}
    
    # Generate valid dates for the next 7 days (including today)
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    
    # Store tuples of (match_label, display_label) to maintain order and nice names
    valid_date_info = []
    # Start from 1 to exclude Today and include only from Tomorrow onwards
    for i in range(1, days_ahead + 1):
        dt = now + timedelta(days=i)
        valid_date_info.append({
            "match": get_spanish_date_str(dt),
            "display": get_full_spanish_date_str(dt)
        })
    
    valid_matches = [d["match"] for d in valid_date_info]
    
    print(f"   Filtering WODs for the next {days_ahead} days: {', '.join(valid_matches)}")
    
    for element in data.get("elements", []):
        day_str = element.get("day")
        if not day_str or day_str not in valid_matches:
            continue
            
        wod_class = element.get("wodClass", "General")
        import html
        element_user = html.unescape(element.get("userName", ""))
        
        # Filter: Only show Crossfit workouts
        if "crossfit" not in wod_class.lower():
            continue
            
        # Filter: Only show workouts for the requested box
        # We normalize both names (remove spaces and special chars) for better matching
        def normalize(s):
            return "".join(c for c in s.lower() if c.isalnum())
        
        target_norm = normalize(box_name)
        element_norm = normalize(element_user)
        
        # Check if the target box name is in the element's user name
        # e.g., 'wezonearturosoria' matches 'Wezone Arturo Soria'
        if target_norm not in element_norm and element_norm not in target_norm:
            # Also try partial matches for common patterns
            if "wezone" in target_norm and "wezone" in element_norm:
                # If both are Wezone but different suburbs, we might need a stricter check
                # But typically subdomain 'wezonearturosoria' is specific enough
                pass
            else:
                continue
            
        full_text_parts = []
        
        # Group exercises from ejerRate by their section (tipoWOD index)
        ejer_by_section = {}
        ejer_rate = element.get("ejerRate", [])
        for ejer in ejer_rate:
            section_idx = ejer.get("tipoWOD")
            if section_idx is None:
                continue
            section_idx = int(section_idx)
            
            # Format the exercise string
            name = ejer.get("ejerName", "")
            # valor1 is usually reps/quantity
            val1_list = ejer.get("valor1", [])
            val1 = val1_list[0] if val1_list and isinstance(val1_list, list) else ""
            # valor2 is usually load/weight
            val2 = ejer.get("valor2", "")
            # notes field (e.g., 'Primera ronda', 'Incremento por ronda')
            notes = ejer.get("notes", "")
            
            # Add 'm' for Run/Row if missing
            unit = ""
            if val1 and any(x in name.lower() for x in ["run", "row"]) and "m" not in name.lower() and "m" not in str(val1).lower():
                unit = "m"
            
            prefix = f"<b>{notes}</b> " if notes else ""
            ejer_str = f"{prefix}{val1}{unit} {name}".strip()
            if val2:
                ejer_str += f" ({val2})"
            
            if section_idx not in ejer_by_section:
                ejer_by_section[section_idx] = []
            ejer_by_section[section_idx].append(ejer_str)

        # Collect from TIPOWODs
        tipos = element.get("TIPOWODs", [])
        for idx, tipo in enumerate(tipos):
            tipo_parts = []
            
            # 1. Title
            title = tipo.get("title")
            if title:
                tipo_parts.append(f"<u>{title}</u>")
            
            # 2. Section Notes
            # We exclude 'notesBreak' to avoid unwanted "Descanso / Rest" labels not in original publication
            for key in ["notes", "notes2"]:
                val = tipo.get(key, "")
                if val:
                    # Skip if it's just repeating the class name
                    if val.strip().upper() == wod_class.upper():
                        continue
                        
                    soup = BeautifulSoup(val, "html.parser")
                    text = soup.get_text(separator="\n")
                    clean = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
                    if clean and clean not in tipo_parts:
                        tipo_parts.append(clean)
            
            # 3. Mapped Exercises from ejerRate
            if idx in ejer_by_section:
                for ejer in ejer_by_section[idx]:
                    if ejer:
                        tipo_parts.append(ejer)
            
            if tipo_parts:
                full_text_parts.append("\n".join(tipo_parts))
        
        # Priority fallback: Only if TIPOWODs provided nothing, check desc/info
        if not full_text_parts:
            for k in ['desc', 'info']:
                val = element.get(k)
                if val and isinstance(val, str):
                    soup = BeautifulSoup(val, "html.parser")
                    text = soup.get_text(separator="\n")
                    clean = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
                    if clean:
                        full_text_parts.append(clean)
        
        # Final assembly
        full_text = "\n\n".join(full_text_parts)
        
        if full_text:
            if day_str not in wods_by_day:
                wods_by_day[day_str] = []
            
            # Use icons based on class name
            prefix = "🏋️"
            class_lower = wod_class.lower()
            if "pulse" in class_lower: prefix = "❤️‍🔥"
            if "endurance" in class_lower: prefix = "🏃"
            if "gymnastics" in class_lower: prefix = "🤸"
            if "halterofilia" in class_lower: prefix = "🏋️‍♀️"
            
            wods_by_day[day_str].append(f"{prefix} <b>{wod_class.upper()}</b>\n{full_text}")
    
    if not wods_by_day:
        msg = f"ℹ️ No workouts found for {box_name} in the next {days_ahead} days."
        print(msg)
        send_telegram_notification(f"ℹ️ No hay entrenamientos publicados en <b>{box_name}</b> para los próximos {days_ahead} días.")
        return True
        
    # Group message into "Day Blocks" and track "Run Days"
    day_blocks = []
    run_days = []
    
    for info in valid_date_info:
        day_match = info["match"]
        if day_match not in wods_by_day:
            continue
            
        wods = wods_by_day[day_match]
        combined_wods_text = "\n\n".join(reversed(wods))
        
        # Check if this day is a "RUN day" (case-insensitive "RUN" as a whole word or part)
        # We check both the text and exercises (which are already in combined_wods_text)
        if "run" in combined_wods_text.lower():
            run_days.append(info["display"])
            
        block = f"🗓 <b>{info['display']}</b>\n"
        block += combined_wods_text
        day_blocks.append(block)

    if not day_blocks:
        return True

    # Assemble chunks based on day blocks to avoid splitting a day in half
    header_parts = [f"📅 <b>AGENDA DE ENTRENAMIENTOS - {box_name}</b>"]
    if run_days:
        header_parts.append("\n🏃‍♂️ <b>RUN days:</b>")
        for rd in run_days:
            header_parts.append(f"• {rd}")
            
    header = "\n".join(header_parts) + "\n\n"
    current_chunk = header
    chunks = []
    
    divider = "\n\n━━━━━━━━━━━━━━━\n\n"
    
    for block in day_blocks:
        # Check if adding this block exceeds limit
        if len(current_chunk) + len(block) + len(divider) > 4000:
            chunks.append(current_chunk.strip())
            current_chunk = block + divider
        else:
            current_chunk += block + divider
            
    if current_chunk:
        chunks.append(current_chunk.strip())

    success = True
    for chunk in chunks:
        # Remove trailing divider if any
        clean_chunk = chunk
        if clean_chunk.endswith("━━━━━━━━━━━━━━━"):
            clean_chunk = clean_chunk[:-15].strip()
            
        if not send_telegram_notification(clean_chunk):
            success = False
            
    return success

def main():
    parser = argparse.ArgumentParser(description="AimHarder Workout Notifier")
    parser.add_argument("--box-name", type=str, default=DEFAULT_BOX_NAME, help="Box name (subdomain)")
    parser.add_argument("--box-id", type=int, default=DEFAULT_BOX_ID, help="Box ID")
    parser.add_argument("--days-ahead", type=int, default=7, help="Number of days to check ahead (default: 7)")
    args = parser.parse_args()
    
    email = os.environ.get("EMAIL")
    password = os.environ.get("PASSWORD")
    
    if not email or not password:
        print("❌ Missing credentials. Set EMAIL and PASSWORD environment variables.")
        sys.exit(1)
    
    session = requests.Session()
    if not login(email, password, session, args.box_name, args.box_id):
        sys.exit(1)
        
    notify_all_workouts(session, args.box_name, args.days_ahead)

if __name__ == "__main__":
    import os
    main()
