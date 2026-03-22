"""
server.py – AimHarder MCP Server

Exposes four tools to AI agents via the Model Context Protocol (MCP):
  • list_classes       – list all classes for a given date
  • book_class         – book a class by ID
  • cancel_booking     – cancel an existing booking
  • find_attendees     – list members booked into a specific class
  • find_attendees_by_name – search for a person across all classes on a date

Usage:
    python server.py                    # stdio transport (default)
    python server.py --transport sse    # SSE transport on http://localhost:8000

Required environment variables (or .env file):
    EMAIL        – AimHarder account email
    PASSWORD     – AimHarder account password
    BOX_NAME     – Box subdomain, e.g. "wezonearturosoria"
    BOX_ID       – Numeric box ID, e.g. 10002
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pytz
from mcp.server.fastmcp import FastMCP

import aimharder_client as ah

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------
TIMEZONE = "Europe/Madrid"

def _get_env(key: str, required: bool = True) -> str:
    val = os.environ.get(key, "").strip()
    if not val and required:
        print(f"❌ Missing required environment variable: {key}", file=sys.stderr)
        sys.exit(1)
    return val


def _parse_date(date_str: str) -> datetime:
    """Parse 'YYYY-MM-DD' into a timezone-aware datetime (Madrid)."""
    tz = pytz.timezone(TIMEZONE)
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid date '{date_str}'. Expected YYYY-MM-DD.") from exc
    return tz.localize(dt)


def _today() -> str:
    """Return today's date in Madrid timezone as YYYY-MM-DD."""
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Session management (cached per process)
# ---------------------------------------------------------------------------
_session: Any = None  # requests.Session once authenticated


def _get_session() -> Any:
    global _session
    if _session is None:
        email = _get_env("EMAIL")
        password = _get_env("PASSWORD")
        box_name = _get_env("BOX_NAME")
        box_id = int(_get_env("BOX_ID"))
        _session = ah.login(email, password, box_name, box_id)
    return _session


def _box() -> tuple[str, int]:
    return _get_env("BOX_NAME"), int(_get_env("BOX_ID"))


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="aimharder",
    instructions=(
        "You are connected to the AimHarder box management system. "
        "Use the available tools to list classes, make/cancel bookings, "
        "and look up who is attending a class."
    ),
)


# ---------------------------------------------------------------------------
# Tool: list_classes
# ---------------------------------------------------------------------------
@mcp.tool()
def list_classes(date: str = "") -> list[dict]:
    """
    List all available classes for a given date.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today (Madrid time).

    Returns:
        A list of class objects. Each object includes:
        - id: unique class identifier (use this for book_class / find_attendees)
        - className: human-readable name (e.g. "CrossFit")
        - timeid: start time + duration (e.g. "0700_60" = 07:00 for 60 min)
        - spots: total capacity
        - bookedSpots: number of booked spots
        - booked: whether the authenticated user is already booked
    """
    target_date = _parse_date(date or _today())
    box_name, box_id = _box()
    session = _get_session()
    classes = ah.list_classes(session, target_date, box_name, box_id)

    # Return a cleaned-up version that is easy for LLMs to reason about
    result = []
    for cls in classes:
        time_raw = cls.get("timeid", cls.get("time", ""))
        if isinstance(time_raw, str) and "_" in time_raw:
            parts = time_raw.split("_")
            t = parts[0]
            duration = parts[1] if len(parts) > 1 else ""
            time_display = f"{t[:2]}:{t[2:]} ({duration} min)" if len(t) == 4 else time_raw
        else:
            time_display = str(time_raw)

        result.append({
            "id": cls.get("id"),
            "className": cls.get("className", cls.get("name", "")),
            "time": time_display,
            "timeid": time_raw,
            "spots": cls.get("aforo", cls.get("spots", cls.get("capacity"))),
            "bookedSpots": cls.get("bookingsCount", cls.get("bookedSpots", cls.get("booked_count"))),
            "booked": bool(cls.get("booked") or cls.get("isBooked") or cls.get("reservada")),
            "waitlist": bool(cls.get("waitList") or cls.get("waitlist")),
            "coach": cls.get("coachName", cls.get("coach", "")),
        })

    return result


# ---------------------------------------------------------------------------
# Tool: book_class
# ---------------------------------------------------------------------------
@mcp.tool()
def book_class(class_id: str, date: str = "") -> dict:
    """
    Book a class by its ID.

    Args:
        class_id: The class ID returned by list_classes.
        date: Date in YYYY-MM-DD format. Defaults to today (Madrid time).

    Returns:
        A result dict with:
        - success: True if the booking was confirmed
        - bookState: raw state from AimHarder (1 = confirmed)
        - message: human-readable explanation
        - raw: full API response for debugging
    """
    target_date = _parse_date(date or _today())
    box_name, box_id = _box()
    session = _get_session()

    raw = ah.book_class(session, class_id, target_date, box_name, box_id)
    book_state = raw.get("bookState")
    error_msg = raw.get("errorMssg", raw.get("bookError", raw.get("error", "")))

    if book_state == 1:
        return {"success": True, "bookState": book_state, "message": "Booking confirmed!", "raw": raw}
    else:
        reason = error_msg or f"bookState={book_state}"
        return {"success": False, "bookState": book_state, "message": reason, "raw": raw}


# ---------------------------------------------------------------------------
# Tool: cancel_booking
# ---------------------------------------------------------------------------
@mcp.tool()
def cancel_booking(class_id: str, date: str = "") -> dict:
    """
    Cancel an existing booking.

    Args:
        class_id: The class ID of the booking to cancel.
        date: Date in YYYY-MM-DD format. Defaults to today (Madrid time).

    Returns:
        A result dict with:
        - success: True if cancellation was successful
        - message: human-readable explanation
        - raw: full API response for debugging
    """
    target_date = _parse_date(date or _today())
    box_name, box_id = _box()
    session = _get_session()

    raw = ah.cancel_booking(session, class_id, target_date, box_name, box_id)
    book_state = raw.get("bookState")
    error_msg = raw.get("errorMssg", raw.get("bookError", raw.get("error", "")))

    # bookState 0 or None after delete typically means cancelled
    success = book_state in (0, None) or raw.get("success") is True
    message = error_msg if not success else "Booking cancelled."
    return {"success": success, "bookState": book_state, "message": message, "raw": raw}


# ---------------------------------------------------------------------------
# Tool: find_attendees
# ---------------------------------------------------------------------------
@mcp.tool()
def find_attendees(class_id: str, date: str = "") -> list[dict]:
    """
    Get the list of members booked into a specific class.

    Args:
        class_id: The class ID returned by list_classes.
        date: Date in YYYY-MM-DD format. Defaults to today (Madrid time).

    Returns:
        A list of attendee objects. Each typically contains:
        - name, surname: member's name
        - id: member ID
    """
    target_date = _parse_date(date or _today())
    box_name, box_id = _box()
    session = _get_session()
    return ah.find_attendees(session, class_id, target_date, box_name, box_id)


# ---------------------------------------------------------------------------
# Tool: find_attendees_by_name
# ---------------------------------------------------------------------------
@mcp.tool()
def find_attendees_by_name(name: str, date: str = "") -> list[dict]:
    """
    Search for a person by name across ALL classes on a given date.

    Useful when you know someone's name but not which class they are in.

    Args:
        name: Partial or full name to search for (case-insensitive).
        date: Date in YYYY-MM-DD format. Defaults to today (Madrid time).

    Returns:
        A list of matches. Each item includes the attendee's info plus a
        'class_info' field with the class id, name, and time.
    """
    target_date = _parse_date(date or _today())
    box_name, box_id = _box()
    session = _get_session()
    return ah.find_attendees_by_name(session, name, target_date, box_name, box_id)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AimHarder MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mode (default: stdio for Claude Desktop / Cursor)",
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for SSE transport (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port for SSE transport (default: 8000)"
    )
    args = parser.parse_args()

    print(f"🏋️  AimHarder MCP server starting (transport={args.transport})…", file=sys.stderr)

    if args.transport == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
