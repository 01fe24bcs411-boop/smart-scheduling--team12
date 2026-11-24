import pytest
from booking_state import *


def run(events):
    r = BookingRequestState(1)
    for e in events:
        r.fire(e)
    return r


def test_tc_st_01_normal_confirmed():
    r = run(["submit", "input_valid", "no_conflict", "commit_success"])
    assert r.state == CONFIRMED


def test_tc_st_02_invalid_input_stays_requested():
    r = run(["submit", "invalid_input", "invalid_input"])
    assert r.state == REQUESTED


def test_tc_st_03_conflict_then_alternative_accepted_then_confirmed():
    r = run(["submit", "input_valid", "conflict", "alternative_found",
             "accept", "no_conflict", "commit_success"])
    assert r.state == CONFIRMED


def test_tc_st_04_conflict_no_alternative_rejected():
    assert run(["submit", "input_valid", "conflict", "no_alternative"]).state == REJECTED


def test_tc_st_05_lock_lost_goes_to_conflict():
    r = run(["submit", "input_valid", "no_conflict", "lock_lost"])
    assert r.state == CONFLICT_DETECTED


def test_tc_st_06_db_failure_rolls_back_to_requested():
    r = run(["submit", "input_valid", "no_conflict", "db_failure"])
    assert r.state == REQUESTED


def test_tc_st_07_cancel_confirmed_then_end():
    r = run(["submit", "input_valid", "no_conflict", "commit_success", "cancel", "close"])
    assert r.state == END and r.is_final()


def test_tc_st_08_rejected_resubmit_and_abandon():
    base = ["submit", "input_valid", "conflict", "no_alternative"]
    assert run(base + ["resubmit"]).state == REQUESTED
    assert run(base + ["abandon"]).state == END


def test_tc_st_09_decline_alternative_rejected():
    r = run(["submit", "input_valid", "conflict", "alternative_found", "decline"])
    assert r.state == REJECTED


@pytest.mark.parametrize("events", [
    ["submit", "commit_success"],                 # cannot confirm before validating
    ["submit", "input_valid", "cancel"],          # cannot cancel an unconfirmed request
    ["submit", "input_valid", "conflict", "commit_success"],  # conflict cannot confirm
])
def test_tc_st_10_illegal_transitions_blocked(events):
    with pytest.raises(InvalidTransition):
        run(events)


def test_tc_st_11_no_events_after_end():
    r = run(["submit", "input_valid", "conflict", "no_alternative", "abandon"])
    assert r.allowed_events() == []
    with pytest.raises(InvalidTransition):
        r.fire("submit")


def test_tc_st_12_all_16_rows_of_table_4_16_present():
    assert len(TRANSITIONS) == 16
