"""E3 - Conflict Detection (Gouri).

Design reference: Sprint 1 section 4.18 (sort bookings by start time + interval
overlap test) and section 4.19 (E2 -> E3 /api/check response format).

Overlap rule: two intervals clash when  start1 < end2 and start2 < end1.
Adjacent intervals (one ends exactly when the other starts) do NOT clash.
"""

# Only confirmed bookings block a slot (assumption: Conflict / Candidate rows
# from the sample dataset are not yet holding the resource).
BLOCKING_STATUSES = {"Confirmed"}


def to_minutes(hhmm):
    """'10:30' -> 630. Raises ValueError for a bad time."""
    try:
        hours, minutes = hhmm.split(":")
        hours, minutes = int(hours), int(minutes)
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid time: {hhmm!r}")
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ValueError(f"Invalid time: {hhmm!r}")
    return hours * 60 + minutes


def is_overlap(start1, end1, start2, end2):
    """Interval overlap test on minute values."""
    return start1 < end2 and start2 < end1


def find_conflicts(request, bookings, resources):
    """Check one request against existing bookings and resource data.

    request   : dict with resource_id, date, start, end, attendees, needs[]
    bookings  : list of booking dicts (as supplied by E2)
    resources : dict resource_id -> resource info (capacity, facilities)

    Returns {"status": "OK" | "CONFLICT", "conflicts": [...]}.
    """
    start = to_minutes(request["start"])
    end = to_minutes(request["end"])
    if end <= start:
        raise ValueError("End time must be after start time")

    conflicts = []

    # --- time conflicts: sort by start time, stop early (single pass) ---
    same_slot = [
        b for b in bookings
        if b["resource_id"] == request["resource_id"]
        and b["date"] == request["date"]
        and b["status"] in BLOCKING_STATUSES
        and b.get("booking_id") != request.get("booking_id")
    ]
    same_slot.sort(key=lambda b: to_minutes(b["start"]))
    for b in same_slot:
        b_start = to_minutes(b["start"])
        if b_start >= end:          # later bookings cannot overlap
            break
        if is_overlap(start, end, b_start, to_minutes(b["end"])):
            conflicts.append({"type": "TIME", "booking_id": b["booking_id"],
                              "detail": f"{b['event']} {b['start']}-{b['end']}"})

    # --- capacity and equipment conflicts ---
    resource = resources.get(request["resource_id"])
    if resource is None:
        conflicts.append({"type": "RESOURCE", "detail": "Unknown resource"})
    else:
        if request["attendees"] > resource["capacity"]:
            conflicts.append({
                "type": "CAPACITY",
                "detail": f"{request['attendees']} attendees > capacity {resource['capacity']}"})
        missing = sorted(n for n in request.get("needs", [])
                         if n not in resource["facilities"])
        if missing:
            conflicts.append({"type": "EQUIPMENT",
                              "detail": "Missing: " + ", ".join(missing)})

    return {"status": "CONFLICT" if conflicts else "OK", "conflicts": conflicts}


if __name__ == "__main__":
    from sample_data import BOOKINGS, RESOURCES
    req = {"booking_id": "B002", "resource_id": "R01", "date": "12 Oct",
           "start": "10:00", "end": "13:00", "attendees": 45,
           "needs": ["projector"]}
    print(find_conflicts(req, BOOKINGS, RESOURCES))
