#!/usr/bin/env python3
"""
AimHarder Bot
Automatically books classes based on a predefined schedule.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import pytz
import requests

# Import shared utilities
from bot_utils import (
    login, send_telegram_notification, get_spanish_date_str, fetch_wod,
    TIMEZONE, DEFAULT_BOX_NAME, DEFAULT_BOX_ID
)


def wait_until_target_time(target_hour: int, target_minute: int, skip_wait: bool = False) -> None:
    """
    Wait until the target booking time (e.g. 7:00 AM Madrid).
    This handles both winter (UTC+1) and summer (UTC+2) time automatically.
    """
    if skip_wait:
        print("⏩ Skipping wait (--skip-wait flag set)")
        return
    
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    
    # Create target time for today
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # If we're past target time, no need to wait
    if now >= target:
        print(f"⏰ Current time ({now.strftime('%H:%M:%S')}) is past target ({target.strftime('%H:%M')}). Proceeding immediately.")
        return
    
    wait_seconds = (target - now).total_seconds()
    print(f"⏳ Current Madrid time: {now.strftime('%H:%M:%S')}")
    print(f"⏳ Target time: {target.strftime('%H:%M:%S')}")
    print(f"⏳ Waiting {wait_seconds:.0f} seconds ({wait_seconds/60:.1f} minutes)...")
    
    # Wait in chunks to show progress
    while True:
        now = datetime.now(tz)
        remaining = (target - now).total_seconds()
        
        if remaining <= 0:
            print("✅ Target time reached! Proceeding with booking...")
            break
        
        # Sleep for min(30 seconds, remaining time)
        sleep_time = min(30, remaining)
        time.sleep(sleep_time)
        
        if remaining > 30:
            print(f"   ⏳ {remaining:.0f}s remaining...")


def load_schedule(path: str = "schedule.json") -> dict:
    """Load the weekly schedule from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)




def get_classes_for_date(session: requests.Session, target_date: datetime, box_name: str, box_id: int) -> list:
    """
    Fetch available classes for a given date.
    """
    date_str = target_date.strftime("%Y%m%d")
    base_url = f"https://{box_name}.aimharder.com"
    bookings_api = f"{base_url}/api/bookings"
    
    params = {
        "box": box_id,
        "day": date_str,
    }
    
    headers = {
        "Accept": "application/json",
        "Referer": base_url,
    }
    
    response = session.get(bookings_api, params=params, headers=headers)
    
    if not response.ok:
        print(f"❌ Failed to fetch classes: {response.status_code}")
        print(f"   Response: {response.text[:500]}")
        return []
    
    try:
        data = response.json()
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return data.get("bookings", data.get("classes", data.get("sessions", [])))
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON response: {response.text[:200]}")
    
    return []


def find_matching_class(classes: list, target_time: str, target_name: str) -> Optional[dict]:
    """
    Find a class matching the target time and name.
    """
    # Normalize target time: "19:00" -> "1900"
    target_time_normalized = target_time.replace(":", "")
    
    for cls in classes:
        # Common field names for time
        class_time = cls.get("timeid", cls.get("time", cls.get("startTime", "")))
        # Common field names for class name
        class_name = cls.get("className", cls.get("name", cls.get("activity", "")))
        
        # Normalize API time format: "0700_60" -> "0700", "07:00" -> "0700"
        if isinstance(class_time, str):
            # Handle "0700_60" format (time_duration)
            if "_" in class_time:
                class_time_normalized = class_time.split("_")[0]
            else:
                # Handle "07:00" or "07:00:00" format
                class_time_normalized = class_time.replace(":", "")[:4]
        else:
            class_time_normalized = str(class_time)
        
        time_match = class_time_normalized == target_time_normalized
        name_match = target_name.lower() in class_name.lower()
        
        if time_match and name_match:
            print(f"✅ Found matching class: {class_name} at {class_time}")
            
            # Check if already booked
            is_booked = cls.get("booked") or cls.get("isBooked") or cls.get("reservada")
            if is_booked:
                print(f"⚠️ Class '{class_name}' at {class_time} appears to be ALREADY BOOKED.")
                cls["_is_already_booked"] = True # Mark for caller
            
            return cls
    
    return None




def fetch_wod(session: requests.Session, box_name: str, target_date: datetime) -> Optional[str]:
    """
    Fetch the WOD for the target date from the main dashboard context.
    The WOD is typically in a timeline feed.
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
        print(f"⚠️ Failed to fetch dashboard: {response.status_code}")
        return None
    import re
    user_id_match = re.search(r"userID:\s*(\d+)", response.text)
    if not user_id_match:
        print("⚠️ Could not find userID in dashboard HTML.")
        return None
    
    user_id = user_id_match.group(1)
    
    # Fetch Activity Feed (AJAX)
    activity_url = f"https://{box_name}.aimharder.com/api/activity"
    params = {
        "timeLineFormat": 0,
        "timeLineContent": 7,
        "userID": user_id
    }
    
    act_response = session.get(activity_url, params=params)
    if not act_response.ok:
        print(f"⚠️ Failed to fetch activity: {act_response.status_code}")
        return None
        
    try:
        data = act_response.json()
    except Exception as e:
        print(f"⚠️ Failed to parse Activity JSON: {e}")
        return None

    target_date_str = get_spanish_date_str(target_date)
    print(f"   Looking for WOD for date: {target_date_str}")
    
    if "elements" not in data:
        print("ℹ️ No 'elements' in activity feed.")
        return None
        
    wods_found = []
    
    for element in data.get("elements", []):
        if element.get("day") == target_date_str:
            wod_class = element.get("wodClass", "General")
            
            # Extract notes from TIPOWODs
            notes_parts = []
            tipos = element.get("TIPOWODs", [])
            for tipo in tipos:
                note_html = tipo.get("notes", "")
                if note_html:
                    # Clean HTML
                    soup_note = BeautifulSoup(note_html, "html.parser")
                    text = soup_note.get_text(separator="\n")
                    notes_parts.append(text.strip())
            
            if notes_parts:
                full_text = "\n\n".join(notes_parts)
                wods_found.append(f"📌 {wod_class}:\n{full_text}")
    
    if not wods_found:
        print(f"ℹ️ No WODs found for {target_date_str} in activity feed.")
    return "\n\n".join(wods_found)


def book_class(session: requests.Session, class_info: dict, target_date: datetime, box_name: str, box_id: int, dry_run: bool = False) -> bool:
    """
    Book the specified class.
    """
    class_id = class_info.get("id", class_info.get("classId", class_info.get("sessionId")))
    class_name = class_info.get("className", class_info.get("name", "Unknown"))
    
    if not class_id:
        print("❌ Could not determine class ID from class info")
        return False
    
    date_str = target_date.strftime("%Y%m%d")
    base_url = f"https://{box_name}.aimharder.com"
    bookings_api = f"{base_url}/api/book"
    
    booking_payload = {
        "id": class_id,
        "day": date_str,
        "insist": 0,
        "familyId": "",
    }
    
    display_time = class_info.get("time", class_info.get("startTime", "Unknown"))
    if isinstance(display_time, str) and "_" in display_time:
        display_time = display_time.split("_")[0]
        if len(display_time) == 4 and display_time.isdigit():
            display_time = f"{display_time[:2]}:{display_time[2:]}"
    
    days_es = {
        "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
        "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
    }
    day_name = days_es.get(target_date.strftime("%A"), target_date.strftime("%A"))
    full_date_str = f"{day_name} {target_date.strftime('%d/%m/%Y')}"
    
    if dry_run:
        print(f"🔵 DRY RUN: Would book class '{class_name}' (ID: {class_id}) for {date_str}")

        send_telegram_notification(
            f"🔵 <b>DRY RUN</b>\n"
            f"<b>Box:</b> {box_name}\n"
            f"<b>Class:</b> {class_name}\n"
            f"<b>Time:</b> {display_time}\n"
            f"<b>Date:</b> {full_date_str}"
        )
        return True
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "Referer": base_url,
    }
    


def main():
    parser = argparse.ArgumentParser(description="AimHarder Bot")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually book, just show what would be booked")
    parser.add_argument("--days-ahead", type=int, default=int(os.environ.get("DAYS_AHEAD", 2)), help="Book for N days ahead (default: 2)")
    parser.add_argument("--schedule", type=str, default="schedule.json", help="Path to schedule JSON file")
    parser.add_argument("--skip-wait", action="store_true", help="Skip waiting for target time (for testing)")
    parser.add_argument("--box-name", type=str, default=None, help="Optional override for box name (subdomain)")
    parser.add_argument("--box-id", type=int, default=None, help="Optional override for box ID")
    parser.add_argument("--target-hour", type=int, default=int(os.environ.get("TARGET_HOUR", 18)), help="Target hour to run (0-23), default: 18")
    parser.add_argument("--target-minute", type=int, default=int(os.environ.get("TARGET_MINUTE", 30)), help="Target minute to run (0-59), default: 30")
    parser.add_argument("--update-status", action="store_true", help="Just update the booking status JSON and exit")
    args = parser.parse_args()
    
    # Get credentials from environment
    email = os.environ.get("EMAIL")
    password = os.environ.get("PASSWORD")
    
    if not email or not password:
        print("❌ Missing credentials. Set EMAIL and PASSWORD environment variables.")
        sys.exit(1)
    
    # Load schedule
    try:
        box = load_schedule(args.schedule)
    except FileNotFoundError:
        print(f"❌ Schedule file not found: {args.schedule}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in schedule file: {e}")
        sys.exit(1)
    
    # Use metadata from JSON if available, otherwise use overrides/defaults
    box_id = box.get("id") or args.box_id or int(os.environ.get("BOX_ID", 0)) or DEFAULT_BOX_ID
    box_name = box.get("name") or args.box_name or os.environ.get("BOX_NAME") or DEFAULT_BOX_NAME
    box_id = int(box_id)

    # Create session and login
    session = requests.Session()
    if not login(email, password, session, box_name, box_id):
        sys.exit(1)

    if args.update_status:
        update_booking_status(session, box, box_name, box_id)
        return
    
    # Determine target date
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    target_date = now + timedelta(days=args.days_ahead)
    day_name = target_date.strftime("%A")
    
    print(f"📅 Target date: {target_date.strftime('%Y-%m-%d')} ({day_name})")
    
    # Check if we should wait
    day_schedule = box.get(day_name)
    if day_schedule:
        wait_until_target_time(args.target_hour, args.target_minute, skip_wait=args.skip_wait)
    else:
        print(f"ℹ️ No classes scheduled for {day_name}.")
        return

    # Process booking
    print(f"\n🚀 Processing Box: {box_name} (ID: {box_id})")
    
    target_time = day_schedule.get("time")
    target_class = day_schedule.get("class_name")
    
    print(f"🎯 Target: {target_class} at {target_time}")
    
    # Fetch classes
    classes = get_classes_for_date(session, target_date, box_name, box_id)
    if not classes:
        print(f"❌ No classes found for {target_date.strftime('%Y-%m-%d')}")
        sys.exit(1)
        
    # Find matching class
    matching_class = find_matching_class(classes, target_time, target_class)
    if not matching_class:
        print(f"❌ No matching class found for {target_class} at {target_time}")
        sys.exit(1)
        
    # Check if already booked
    if matching_class.get("_is_already_booked"):
        print(f"ℹ️ Skipping booking: Already booked.")
        return
        
    # Book
    book_class(session, matching_class, target_date, box_name, box_id, dry_run=args.dry_run)

    print("\n🏁 Finished processing box.")


if __name__ == "__main__":
    main()
