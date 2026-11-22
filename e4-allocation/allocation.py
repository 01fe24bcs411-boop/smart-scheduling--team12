"""E4 - Resource Allocation & Concurrency Control (Kesar).

Design reference: Sprint 1 section 4.13 / 4.18: best-fit selection (smallest
room that fits), priority rules, mutex lock with timeout, first-successful-wins,
commit through E2.

Note: the lock protects threads inside one running server process. E2's
BEGIN IMMEDIATE + re-check is the second barrier (also across processes).
"""
import os
import sys
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
for _f in ("e2-database", "e3-conflict"):
    sys.path.insert(0, os.path.join(_HERE, "..", _f))

import database as db                           # E2
from conflict_detection import find_conflicts   # E3

_LOCK = threading.Lock()
DEFAULT_LOCK_TIMEOUT = 5.0


def best_fit(free_resources):
    """Smallest capacity first (saves large rooms); resource id breaks ties."""
    if not free_resources:
        return None
    return min(free_resources, key=lambda r: (r["capacity"], r["resource_id"]))


def sort_by_priority(requests):
    """Higher priority first; equal priority keeps arrival order (first come, first served)."""
    return sorted(requests, key=lambda r: -int(r.get("priority", 1)))


def allocate(db_path, request, lock_timeout=DEFAULT_LOCK_TIMEOUT):
    """Allocate and commit one request.

    request: event_id, date, start, end, attendees, needs[], optional resource_id
             (if missing, best-fit picks the room), optional equipment{id: qty}.
    Returns {"status": "CONFIRMED", "booking_id", "resource_id"} or
            {"status": "REJECTED", "reason": "..."}.
    """
    if not _LOCK.acquire(timeout=lock_timeout):
        return {"status": "REJECTED", "reason": "Lock timeout - try again"}
    conn = None
    try:
        conn = db.connect(db_path)
        resources = db.get_resources(conn)
        resource_id = request.get("resource_id")
        if resource_id is None:
            choice = best_fit(db.free_resources(conn, request["date"], request["start"],
                                                request["end"], request["attendees"],
                                                request.get("needs", [])))
            if choice is None:
                return {"status": "REJECTED", "reason": "No suitable free resource"}
            resource_id = choice["resource_id"]

        check = find_conflicts({**request, "resource_id": resource_id},
                               db.get_bookings(conn, date=request["date"]), resources)
        if check["status"] != "OK":
            return {"status": "REJECTED", "conflicts": check["conflicts"],
                    "reason": "; ".join(c["detail"] for c in check["conflicts"])}

        result = db.commit_booking(conn, request["event_id"], resource_id, request["date"],
                                   request["start"], request["end"], request.get("equipment"))
        if result["status"] == "COMMITTED":
            return {"status": "CONFIRMED", "booking_id": result["booking_id"],
                    "resource_id": resource_id}
        return {"status": "REJECTED", "reason": result["reason"]}
    except ValueError as exc:                       # bad time format from E3
        return {"status": "REJECTED", "reason": str(exc)}
    finally:
        if conn is not None:
            conn.close()
        _LOCK.release()


def process_queue(db_path, requests, lock_timeout=DEFAULT_LOCK_TIMEOUT):
    """Process a batch in priority order. Returns [(request, result), ...]."""
    return [(r, allocate(db_path, r, lock_timeout)) for r in sort_by_priority(requests)]
