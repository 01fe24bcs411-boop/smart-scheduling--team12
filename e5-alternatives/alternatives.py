"""E5 - Alternative Recommendation (Kesar and Gouri).

Design reference: Sprint 1 section 4.18: free-room search for the same slot,
else nearest-free-slot search, ranked by closeness. Reads free rooms and slots
from E2. The organizer decides - E5 only suggests.

Assumptions (change here if the department differs): the working day is
08:00-18:00 and slots are searched every 30 minutes.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _f in ("e2-database", "e3-conflict"):
    sys.path.insert(0, os.path.join(_HERE, "..", _f))

import database as db
from conflict_detection import to_minutes

DAY_START, DAY_END, STEP_MIN = "08:00", "18:00", 30


def to_hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _option(kind, res, date, start, end, reason, needed):
    return {"kind": kind, "resource_id": res["resource_id"], "name": res["name"],
            "capacity": res["capacity"], "date": date, "start": start, "end": end,
            "reason": reason, "spare_seats": res["capacity"] - needed}


def suggest_alternatives(conn, request, limit=5, day_start=DAY_START,
                         day_end=DAY_END, step=STEP_MIN):
    """Return ranked options: free rooms for the same slot, else nearest free slots."""
    date, start, end = request["date"], request["start"], request["end"]
    need, needs = request["attendees"], request.get("needs", [])
    original = request.get("resource_id")

    # 1. same slot, another suitable free room (smallest spare capacity first)
    rooms = [r for r in db.free_resources(conn, date, start, end, need, needs)
             if r["resource_id"] != original]
    if rooms:
        return [_option("ROOM", r, date, start, end, "Free for the same slot", need)
                for r in rooms][:limit]

    # 2. nearest free slot (same length) on any suitable room
    s0, e0 = to_minutes(start), to_minutes(end)
    length = e0 - s0
    suitable = [r for r in db.get_resources(conn).values()
                if r["capacity"] >= need and {n.lower() for n in needs} <= r["facilities"]]
    found = []
    for res in suitable:
        for s in range(to_minutes(day_start), to_minutes(day_end) - length + 1, step):
            if s == s0 and res["resource_id"] == original:
                continue
            if db.is_available(conn, res["resource_id"], date, to_hhmm(s), to_hhmm(s + length)):
                found.append((abs(s - s0), res["capacity"], res["resource_id"], s, res))
    found.sort(key=lambda t: t[:3])
    return [_option("SLOT", res, date, to_hhmm(s), to_hhmm(s + length),
                    f"Nearest free slot ({dist} min from requested)", need)
            for dist, _cap, _rid, s, res in found[:limit]]
