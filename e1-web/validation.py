"""E1 - form validation: reject bad data early (Sprint 1 section 4.18)."""
import re
from datetime import datetime

_TIME = re.compile(r"^\d{2}:\d{2}$")


def _clean_needs(value):
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip().lower() for v in value if str(v).strip()]


def _int(value, low, high):
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return n if low <= n <= high else None


def validate_event_form(form):
    """Return (clean, errors). errors is {field: message}; empty means valid."""
    errors, clean = {}, {}

    title = str(form.get("eventName", "")).strip()
    if not title:
        errors["eventName"] = "Event name is required"
    clean["title"] = title

    resource_id = str(form.get("resourceId", "")).strip()
    if not resource_id:
        errors["resourceId"] = "Resource is required"
    clean["resource_id"] = resource_id

    date = str(form.get("date", "")).strip()
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        errors["date"] = "Date must look like 2026-10-12"
    clean["date"] = date

    times = {}
    for key in ("start", "end"):
        value = str(form.get(key, "")).strip()
        if not _TIME.match(value):
            errors[key] = "Time must look like 09:30"
        else:
            try:
                datetime.strptime(value, "%H:%M")
                times[key] = value
            except ValueError:
                errors[key] = "Not a valid time"
        clean[key] = value
    if len(times) == 2 and times["end"] <= times["start"]:
        errors["end"] = "End time must be after start time"

    attendees = _int(form.get("attendees"), 1, 10000)
    if attendees is None:
        errors["attendees"] = "Attendees must be a whole number from 1 to 10000"
    clean["attendees"] = attendees

    priority = _int(form.get("priority", 1) or 1, 1, 5)
    if priority is None:
        errors["priority"] = "Priority must be 1 to 5"
    clean["priority"] = priority or 1

    clean["needs"] = _clean_needs(form.get("needs"))
    return clean, errors


def validate_resource_form(form):
    errors, clean = {}, {}
    name = str(form.get("name", "")).strip()
    if not name:
        errors["name"] = "Name is required"
    clean["name"] = name
    rtype = str(form.get("type", "")).strip()
    if not rtype:
        errors["type"] = "Type is required (Lab, Hall, Classroom...)"
    clean["type"] = rtype
    capacity = _int(form.get("capacity"), 1, 10000)
    if capacity is None:
        errors["capacity"] = "Capacity must be a whole number from 1 to 10000"
    clean["capacity"] = capacity
    clean["facilities"] = _clean_needs(form.get("facilities"))
    return clean, errors
