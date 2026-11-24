state-machine/booking_state.py"""
Booking request state machine  (Sprint 1, Section 4.16 State Diagram, D6)

States and transitions are copied one-to-one from the approved state table.
Nothing here changes the approved design; it only enforces it in code.
"""
from datetime import datetime

START = "Start"
REQUESTED = "Requested"
VALIDATING = "Validating"
ALLOCATING = "Allocating"
CONFLICT_DETECTED = "Conflict Detected"
ALTERNATIVE_SUGGESTED = "Alternative Suggested"
CONFIRMED = "Confirmed"
REJECTED = "Rejected"
CANCELLED = "Cancelled"
END = "End"

# (current state, event) -> next state     [row numbers = rows of table 4.16]
TRANSITIONS = {
    (START, "submit"): REQUESTED,                         # 1
    (REQUESTED, "invalid_input"): REQUESTED,              # 2 validation message, correct
    (REQUESTED, "input_valid"): VALIDATING,               # 3
    (VALIDATING, "no_conflict"): ALLOCATING,              # 4 E3 sort + overlap passes
    (VALIDATING, "conflict"): CONFLICT_DETECTED,          # 5 overlap/capacity/equipment
    (ALLOCATING, "commit_success"): CONFIRMED,            # 6 best-fit, lock won, commit ok
    (ALLOCATING, "lock_lost"): CONFLICT_DETECTED,         # 7 slot already taken
    (ALLOCATING, "db_failure"): REQUESTED,                # 8 rollback, retry
    (CONFLICT_DETECTED, "alternative_found"): ALTERNATIVE_SUGGESTED,  # 9  E5
    (CONFLICT_DETECTED, "no_alternative"): REJECTED,      # 10
    (ALTERNATIVE_SUGGESTED, "accept"): VALIDATING,        # 11 re-check
    (ALTERNATIVE_SUGGESTED, "decline"): REJECTED,         # 12
    (REJECTED, "resubmit"): REQUESTED,                    # 13
    (REJECTED, "abandon"): END,                           # 14
    (CONFIRMED, "cancel"): CANCELLED,                     # 15 slot freed at once
    (CANCELLED, "close"): END,                            # 16
}


class InvalidTransition(Exception):
    """Raised when an event is not allowed in the current state."""


class BookingRequestState:
    def __init__(self, request_id=None):
        self.request_id = request_id
        self.state = START
        self.history = []          # list of (time, from, event, to)

    def fire(self, event):
        key = (self.state, event)
        if key not in TRANSITIONS:
            raise InvalidTransition(
                f"Event '{event}' not allowed in state '{self.state}'")
        old, new = self.state, TRANSITIONS[key]
        self.state = new
        self.history.append((datetime.now().strftime("%H:%M:%S"), old, event, new))
        return new

    def allowed_events(self):
        return sorted(e for (s, e) in TRANSITIONS if s == self.state)

    def is_final(self):
        return self.state == END


def allowed_events_from(state):
    return sorted(e for (s, e) in TRANSITIONS if s == state)
