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

# --- Configuration ---
LOGIN_URL = "https://login.aimharder.com/"
TIMEZONE = "Europe/Madrid"


# Default box configuration (can be overridden via CLI or env vars)
DEFAULT_BOX_NAME = "wezonearturosoria"
DEFAULT_BOX_ID = 10002


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


def login(email: str, password: str, session: requests.Session, box_name: str, box_id: int) -> bool:
    """
    Authenticate with AimHarder.
    Returns True if login is successful.
    """
    # AimHarder uses a centralized login portal
    login_payload = {
        "email": email,
        "password": password,
        "box": box_id,
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://login.aimharder.com",
        "Referer": "https://login.aimharder.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    
    response = session.post(LOGIN_URL, data=login_payload, headers=headers, allow_redirects=True)
    
    # Check if we got redirected to the box page (successful login)
    if response.ok and box_name in response.url:
        print(f"✅ Login successful! Redirected to: {response.url}")
        return True
    
    # Alternative: check for session cookies
    if "PHPSESSID" in session.cookies.get_dict() or any("aim" in c.lower() for c in session.cookies.get_dict()):
        print("✅ Login successful (session cookie obtained)")
        return True
    
    print(f"❌ Login failed. Status: {response.status_code}")
    print(f"   Response URL: {response.url}")
    return False


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
        # The response structure may vary - common patterns:
        # - { "bookings": [...] }
        # - { "classes": [...] }
        # - Direct array [...]
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
            return cls
    
    return None


def book_class(session: requests.Session, class_info: dict, target_date: datetime, box_name: str, box_id: int, dry_run: bool = False) -> bool:
    """
    Book the specified class.
    """
    class_id = class_info.get("id", class_info.get("classId", class_info.get("sessionId")))
    class_name = class_info.get("className", class_info.get("name", "Unknown"))
    
    if not class_id:
        print("❌ Could not determine class ID from class info")
        print(f"   Class info keys: {class_info.keys()}")
        return False
    
    date_str = target_date.strftime("%Y%m%d")
    base_url = f"https://{box_name}.aimharder.com"
    bookings_api = f"{base_url}/api/bookings"
    
    booking_payload = {
        "id": class_id,
        "box": box_id,
        "day": date_str,
    }
    
    if dry_run:
        print(f"🔵 DRY RUN: Would book class '{class_name}' (ID: {class_id}) for {date_str}")
        print(f"   Payload: {booking_payload}")
        return True
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "Referer": base_url,
    }
    
    response = session.post(bookings_api, data=booking_payload, headers=headers)
    
    if response.ok:
        print(f"✅ Successfully booked: {class_name}")
        try:
            result = response.json()
            print(f"   Response: {result}")
        except json.JSONDecodeError:
            pass
        return True
    else:
        print(f"❌ Booking failed: {response.status_code}")
        print(f"   Response: {response.text[:500]}")
        return False


def main():
    parser = argparse.ArgumentParser(description="AimHarder Bot")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually book, just show what would be booked")
    parser.add_argument("--days-ahead", type=int, default=2, help="Book for N days ahead (default: 2)")
    parser.add_argument("--schedule", type=str, default="schedule.json", help="Path to schedule JSON file")
    parser.add_argument("--skip-wait", action="store_true", help="Skip waiting for target time (for testing)")
    parser.add_argument("--box-name", type=str, default=None, help="Box name (subdomain), e.g. 'wezonearturosoria'")
    parser.add_argument("--box-id", type=int, default=None, help="Box ID, e.g. 10584")
    parser.add_argument("--target-hour", type=int, default=int(os.environ.get("TARGET_HOUR", 7)), help="Target hour to run (0-23), default: 7")
    parser.add_argument("--target-minute", type=int, default=int(os.environ.get("TARGET_MINUTE", 0)), help="Target minute to run (0-59), default: 0")
    args = parser.parse_args()
    
    # Get box configuration from args, env vars, or defaults
    box_name = args.box_name or os.environ.get("BOX_NAME") or DEFAULT_BOX_NAME
    box_id = args.box_id or int(os.environ.get("BOX_ID", 0)) or DEFAULT_BOX_ID
    
    print(f"🏋️ Box: {box_name} (ID: {box_id})")
    
    # Wait until target time (7:00 AM Madrid) before proceeding
    wait_until_target_time(args.target_hour, args.target_minute, skip_wait=args.skip_wait)
    
    # Get credentials from environment
    email = os.environ.get("EMAIL")
    password = os.environ.get("PASSWORD")
    
    if not email or not password:
        print("❌ Missing credentials. Set EMAIL and PASSWORD environment variables.")
        sys.exit(1)
    
    # Load schedule
    try:
        schedule = load_schedule(args.schedule)
    except FileNotFoundError:
        print(f"❌ Schedule file not found: {args.schedule}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in schedule file: {e}")
        sys.exit(1)
    
    # Determine target date
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    target_date = now + timedelta(days=args.days_ahead)
    day_name = target_date.strftime("%A")
    
    print(f"📅 Target date: {target_date.strftime('%Y-%m-%d')} ({day_name})")
    
    # Check if there's a class scheduled for this day
    day_schedule = schedule.get(day_name)
    if not day_schedule:
        print(f"ℹ️ No class scheduled for {day_name}. Exiting.")
        sys.exit(0)
    
    target_time = day_schedule.get("time")
    target_class = day_schedule.get("class_name")
    
    print(f"🎯 Looking for: {target_class} at {target_time}")
    
    # Create session and login
    session = requests.Session()
    
    if not login(email, password, session, box_name, box_id):
        print("❌ Authentication failed. Check your credentials.")
        sys.exit(1)
    
    # Fetch classes for target date
    classes = get_classes_for_date(session, target_date, box_name, box_id)
    
    if not classes:
        print(f"❌ No classes found for {target_date.strftime('%Y-%m-%d')}")
        sys.exit(1)
    
    print(f"📋 Found {len(classes)} classes for {day_name}")
    
    # Find matching class
    matching_class = find_matching_class(classes, target_time, target_class)
    
    if not matching_class:
        print(f"❌ No matching class found for {target_class} at {target_time}")
        print("   Available classes:")
        for cls in classes[:10]:  # Show first 10 classes
            name = cls.get("className", cls.get("name", "?"))
            time = cls.get("timeid", cls.get("time", "?"))
            print(f"   - {name} at {time}")
        sys.exit(1)
    
    # Book the class
    success = book_class(session, matching_class, target_date, box_name, box_id, dry_run=args.dry_run)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
