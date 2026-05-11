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
    send_telegram_notification,
    TIMEZONE, DEFAULT_BOX_NAME, DEFAULT_BOX_ID
)
from client import AimHarderClient
from exceptions import BookingFailed, IncorrectCredentials, TooManyWrongAttempts


def wait_until_target_time(target_hour: int, target_minute: int, skip_wait: bool = False) -> None:
    """
    Wait until the target booking time (e.g. 12:00 Madrid).
    Handles both winter (UTC+1) and summer (UTC+2) automatically.
    Sleeps 1s past the target so the booking window is guaranteed to be open.
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
            # Sleep 1s past the target so the booking window is open
            time.sleep(1)
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





def print_and_notify_booking(box_name: str, class_name: str, display_time: str, full_date_str: str, status: str, err: str = ""):
    if status == "CONFIRMED":
        print(f"✅ Successfully booked '{class_name}' at {display_time} on {full_date_str}")
        msg = (
            f"✅ <b>Booking CONFIRMED</b>\n"
            f"<b>Box:</b> {box_name}\n"
            f"<b>Class:</b> {class_name}\n"
            f"<b>Time:</b> {display_time}\n"
            f"<b>Date:</b> {full_date_str}"
        )
    elif status == "DRY_RUN":
        print(f"🔵 DRY RUN: Would book class '{class_name}' for {full_date_str}")
        msg = (
            f"🔵 <b>DRY RUN</b>\n"
            f"<b>Box:</b> {box_name}\n"
            f"<b>Class:</b> {class_name}\n"
            f"<b>Time:</b> {display_time}\n"
            f"<b>Date:</b> {full_date_str}"
        )
    else:
        print(f"❌ Booking failed. {err}")
        msg = (
            f"❌ <b>Booking FAILED</b>\n"
            f"<b>Box:</b> {box_name}\n"
            f"<b>Class:</b> {class_name}\n"
            f"<b>Time:</b> {display_time}\n"
            f"<b>Date:</b> {full_date_str}\n"
            f"<b>Reason:</b> {err}"
        )
    send_telegram_notification(msg)

def process_booking(client: AimHarderClient, class_info: dict, target_date: datetime, dry_run: bool = False) -> bool:
    class_id = class_info.get("id", class_info.get("classId", class_info.get("sessionId")))
    class_name = class_info.get("className", class_info.get("name", "Unknown"))
    if not class_id:
        print("❌ Could not determine class ID from class info")
        return False
        
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
        print_and_notify_booking(client.box_name, class_name, display_time, full_date_str, "DRY_RUN")
        return True

    try:
        resp = client.book_class(class_id, target_date)
        book_state = resp.get("bookState")
        if book_state == 1:
            print_and_notify_booking(client.box_name, class_name, display_time, full_date_str, "CONFIRMED")
            return True
        else:
            reason = resp.get("errorMssg", resp.get("bookError", resp.get("error", ""))) or f"bookState={book_state}"
            print_and_notify_booking(client.box_name, class_name, display_time, full_date_str, "FAILED", reason)
            return False
    except Exception as e:
        print_and_notify_booking(client.box_name, class_name, display_time, full_date_str, "FAILED", str(e))
        return False



def main():
    parser = argparse.ArgumentParser(description="AimHarder Bot")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually book, just show what would be booked")
    parser.add_argument("--days-ahead", type=int, default=int(os.environ.get("DAYS_AHEAD", 2)), help="Book for N days ahead (default: 2)")
    parser.add_argument("--schedule", type=str, default="schedule.json", help="Path to schedule JSON file")
    parser.add_argument("--skip-wait", action="store_true", help="Skip waiting for target time (for testing)")
    parser.add_argument("--box-name", type=str, default=None, help="Optional override for box name (subdomain)")
    parser.add_argument("--box-id", type=int, default=None, help="Optional override for box ID")
    # TARGET_HOUR_GMT1: booking open hour in GMT+1 / Madrid local time (Europe/Madrid).
    # Falls back to TARGET_HOUR for backwards compatibility.
    _default_hour = int(os.environ.get("TARGET_HOUR_GMT1", os.environ.get("TARGET_HOUR", 18)))
    parser.add_argument("--target-hour", type=int, default=_default_hour, help="Target hour in Madrid time (0-23) to trigger booking, default: 18")
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

    try:
        client = AimHarderClient(email, password, box_name, box_id)
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(1)

    if args.update_status:
        # Assuming update_booking_status was defined somewhere or ignored
        # update_booking_status(client.session, box, box_name, box_id)
        return
    
    # Determine target date
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    target_date = now + timedelta(days=args.days_ahead)
    day_name = target_date.strftime("%A")
    
    print(f"📅 Target date: {target_date.strftime('%Y-%m-%d')} ({day_name})")
    
    # Check if we should wait
    day_schedule = box.get(day_name)
    print(f"📅 day_schedule:" ,day_schedule)


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
    
    try:
        classes = client.list_classes(target_date)
    except Exception as e:
        print(f"❌ Error fetching classes: {e}")
        classes = []
        
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
        

    # Book the class
    success = process_booking(client, matching_class, target_date, dry_run=args.dry_run)

    if success:
        print("\n🏁 Booking completed successfully.")
    else:
        print("\n❌ Booking failed. Check the logs above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
