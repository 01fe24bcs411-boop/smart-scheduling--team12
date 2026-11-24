"""Prints a state trace for each scenario of the approved state diagram (4.16)."""
from booking_state import BookingRequestState

SCENARIOS = {
    "A. Normal booking (no conflict)":
        ["submit", "input_valid", "no_conflict", "commit_success"],
    "B. Conflict -> alternative accepted -> confirmed (B002 vs B001, Lab 2)":
        ["submit", "input_valid", "conflict", "alternative_found",
         "accept", "no_conflict", "commit_success"],
    "C. Two organizers, same slot: lock lost -> alternatives":
        ["submit", "input_valid", "no_conflict", "lock_lost", "alternative_found"],
    "D. Conflict, no feasible alternative -> rejected -> abandoned":
        ["submit", "input_valid", "conflict", "no_alternative", "abandon"],
    "E. Database failure -> rollback -> retry -> confirmed -> cancelled":
        ["submit", "input_valid", "no_conflict", "db_failure",
         "input_valid", "no_conflict", "commit_success", "cancel", "close"],
}

for title, events in SCENARIOS.items():
    r = BookingRequestState(request_id=title[0])
    print(f"\n=== {title}")
    for e in events:
        r.fire(e)
    for t, old, ev, new in r.history:
        print(f"  {t}  {old:<22} --{ev}--> {new}")
    print(f"  FINAL STATE: {r.state}")

print("\n=== Illegal transition check")
r = BookingRequestState(99)
r.fire("submit")
try:
    r.fire("commit_success")
except Exception as ex:
    print("  BLOCKED:", ex)
