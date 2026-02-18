#!/usr/bin/env python3
"""
AimHarder Workout Notifier
Fetches CrossFit workout details from AimHarder activity feed and sends Telegram notifications.
"""
import argparse
import sys
import os
import requests
import re
import html
import pytz
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from bot_utils import (
    login, send_telegram_notification, get_spanish_date_str, 
    get_full_spanish_date_str,
    TIMEZONE, DEFAULT_BOX_NAME, DEFAULT_BOX_ID
)


def normalize(s):
    """
    Normalize a string by removing spaces and special characters for matching.
    Example: 'Wezone Arturo Soria' -> 'wezonearturosoria'
    """
    return "".join(c for c in s.lower() if c.isalnum())


def notify_all_workouts(session: requests.Session, box_name: str, days_ahead: int = 1) -> bool:
    """
    Fetch CrossFit workouts from the activity feed and send a Telegram notification.
    
    Args:
        session: Authenticated requests session
        box_name: Box subdomain name (e.g., 'wezonearturosoria')
        days_ahead: Number of days to fetch workouts for (starting from tomorrow)
    
    Returns:
        True if successful, False otherwise
    """
    # ============================================================================
    # STEP 1: Fetch dashboard to extract user ID
    # ============================================================================
    url = f"https://{box_name}.aimharder.com/"
    print(f"🔄 Fetching all WODs from {url}...")
    
    response = session.get(url)
    if not response.ok:
        print(f"⚠️ Failed to fetch dashboard: {response.status_code}")
        return False

    # Extract user ID from dashboard HTML
    user_id_match = re.search(r"userID:\s*(\d+)", response.text)
    if not user_id_match:
        print("⚠️ Could not find userID in dashboard HTML.")
        return False
    
    user_id = user_id_match.group(1)
    
    # ============================================================================
    # STEP 2: Fetch activity feed data
    # ============================================================================
    activity_url = f"https://{box_name}.aimharder.com/api/activity"
    print(f"🔄 activity_url: {activity_url}")
    params = {
        "timeLineFormat": 0,
        "timeLineContent": 100,  # Fetch up to 100 activity items
        "userID": user_id
    }
    
    act_response = session.get(activity_url, params=params)
    print(f"🔄 act_response: {act_response}")
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
    
    # ============================================================================
    # STEP 3: Generate date range for filtering
    # ============================================================================
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    
    # Build list of valid dates (starting from tomorrow)
    valid_date_info = []
    # print(f"   data: {data}")
    for i in range(1, days_ahead + 1):
        dt = now + timedelta(days=i)
        valid_date_info.append({
            "match": get_spanish_date_str(dt),      # Short format for matching (e.g., "11 Feb")
            "display": get_full_spanish_date_str(dt) # Full format for display (e.g., "Martes 11 Feb")
        })
    
    valid_matches = [d["match"] for d in valid_date_info]

    print(f"   Filtering WODs for the next {days_ahead} days: {', '.join(valid_matches)}")
    
    # ============================================================================
    # STEP 4: Process activity feed elements and extract CrossFit workouts
    # ============================================================================
    wods_by_day = {}  # Dictionary to store workouts grouped by day
    
    target_norm = normalize(box_name)  # Pre-calculate normalized box name

    for element in data.get("elements", []):
        
        # --- Filter by date ---
        day_str = element.get("day")
        if not day_str or day_str not in valid_matches:
            continue
        
        # --- Filter by class type (CrossFit only) ---
        wod_class = element.get("wodClass", "General")
        print(f"   wod_class: {wod_class}")
        # if "crossfit" not in wod_class.lower():
        #     continue
        
        # --- Filter by box name ---
        element_user = html.unescape(element.get("userName", ""))
        element_norm = normalize(element_user)
        
        # Check if this workout belongs to the requested box
        if target_norm not in element_norm and element_norm not in target_norm:
            # Special case: allow partial match for Wezone boxes
            if "wezone" in target_norm and "wezone" in element_norm:
                pass  # Accept it
            else:
                continue  # Skip this element
        
        # --- Extract workout content ---
        full_text_parts = []
        
        # Group exercises by their section index
        ejer_by_section = {}
        ejer_rate = element.get("ejerRate", [])
        
        for ejer in ejer_rate:
            section_idx = ejer.get("tipoWOD")
            if section_idx is None:
                continue
            section_idx = int(section_idx)
            
            # Extract exercise details
            name = ejer.get("ejerName", "")
            val1_list = ejer.get("valor1", [])
            val1 = val1_list[0] if val1_list and isinstance(val1_list, list) else ""
            val2 = ejer.get("valor2", "")  # Weight/load
            notes = ejer.get("notes", "")  # Round info, etc.
            
            # Add unit for running/rowing if missing
            unit = ""
            if val1 and any(x in name.lower() for x in ["run", "row"]):
                if "m" not in name.lower() and "m" not in str(val1).lower():
                    unit = "m"
            
            # Format exercise string
            prefix = f"<b>{notes}</b> " if notes else ""
            ejer_str = f"{prefix}{val1}{unit} {name}".strip()
            if val2:
                ejer_str += f" ({val2})"
            
            # Add to section
            if section_idx not in ejer_by_section:
                ejer_by_section[section_idx] = []
            ejer_by_section[section_idx].append(ejer_str)
        
        # Process workout sections (TIPOWODs)
        tipos = element.get("TIPOWODs", [])
        for idx, tipo in enumerate(tipos):
            tipo_parts = []
            
            # Add section title
            title = tipo.get("title")
            if title:
                tipo_parts.append(f"<u>{title}</u>")
            
            # Add section notes (excluding redundant class name)
            for key in ["notes", "notes2"]:
                val = tipo.get(key, "")
                if val:
                    # Skip if it just repeats the class name
                    if val.strip().upper() == wod_class.upper():
                        continue
                    
                    # Parse HTML and clean up
                    soup = BeautifulSoup(val, "html.parser")
                    text = soup.get_text(separator="\n")
                    clean = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
                    if clean and clean not in tipo_parts:
                        tipo_parts.append(clean)
            
            # Add exercises for this section
            if idx in ejer_by_section:
                for ejer in ejer_by_section[idx]:
                    if ejer:
                        tipo_parts.append(ejer)
            
            if tipo_parts:
                full_text_parts.append("\n".join(tipo_parts))
        
        # Fallback: if no TIPOWODs content, try desc/info fields
        if not full_text_parts:
            for k in ['desc', 'info']:
                val = element.get(k)
                if val and isinstance(val, str):
                    soup = BeautifulSoup(val, "html.parser")
                    text = soup.get_text(separator="\n")
                    clean = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
                    if clean:
                        full_text_parts.append(clean)
        
        # Assemble final workout text
        full_text = "\n\n".join(full_text_parts)
        
        if full_text:
            if day_str not in wods_by_day:
                wods_by_day[day_str] = []
            
            wods_by_day[day_str].append(f"🏋️ <b>{wod_class.upper()}</b>\n{full_text}")
    
    # ============================================================================
    # STEP 5: Build and send Telegram notification
    # ============================================================================
    if not wods_by_day:
        msg = f"ℹ️ No workouts found for {box_name} in the next {days_ahead} days."
        print(msg)
        send_telegram_notification(f"ℹ️ No hay entrenamientos publicados en <b>{box_name}</b> para los próximos {days_ahead} días.")
        return True
    
    # Build day blocks and track run days
    day_blocks = []
    run_days = []
    
    for info in valid_date_info:
        day_match = info["match"]
        if day_match not in wods_by_day:
            continue
        
        wods = wods_by_day[day_match]
        combined_wods_text = "\n\n".join(reversed(wods))
        
        # Check if this is a run day
        if "run" in combined_wods_text.lower():
            run_days.append(info["display"])
        
        block = f"🗓 <b>{info['display']}</b>\n"
        block += combined_wods_text
        day_blocks.append(block)
    
    if not day_blocks:
        return True
    
    # Build message header
    header_parts = [f"📅 <b>AGENDA DE ENTRENAMIENTOS - {box_name}</b>"]
    if run_days:
        header_parts.append("\n🏃‍♂️ <b>RUN days:</b>")
        for rd in run_days:
            header_parts.append(f"• {rd}")
    
    header = "\n".join(header_parts) + "\n\n"
    
    # Split into chunks if needed (Telegram has a 4096 character limit)
    current_chunk = header
    chunks = []
    divider = "\n\n━━━━━━━━━━━━━━━\n\n"
    
    for block in day_blocks:
        if len(current_chunk) + len(block) + len(divider) > 4000:
            chunks.append(current_chunk.strip())
            current_chunk = block + divider
        else:
            current_chunk += block + divider
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # Send all chunks
    success = True
    for chunk in chunks:
        # Remove trailing divider
        clean_chunk = chunk
        if clean_chunk.endswith("━━━━━━━━━━━━━━━"):
            clean_chunk = clean_chunk[:-15].strip()
        
        if not send_telegram_notification(clean_chunk):
            success = False
    
    return success


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="AimHarder Workout Notifier")
    parser.add_argument("--box-name", type=str, default=DEFAULT_BOX_NAME, 
                       help="Box name (subdomain)")
    parser.add_argument("--box-id", type=int, default=DEFAULT_BOX_ID, 
                       help="Box ID")
    parser.add_argument("--days-ahead", type=int, default=1, 
                       help="Number of days to check ahead (default: 1s)")
    args = parser.parse_args()
    
    # Get credentials from environment
    email = os.environ.get("EMAIL")
    password = os.environ.get("PASSWORD")
    
    if not email or not password:
        print("❌ Missing credentials. Set EMAIL and PASSWORD environment variables.")
        sys.exit(1)
    
    # Login and fetch workouts
    session = requests.Session()
    if not login(email, password, session, args.box_name, args.box_id):
        sys.exit(1)
    
    notify_all_workouts(session, args.box_name, args.days_ahead)


if __name__ == "__main__":
    main()
