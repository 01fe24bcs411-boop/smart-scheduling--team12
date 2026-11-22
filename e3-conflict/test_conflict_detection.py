import time
import pytest
from conflict_detection import find_conflicts, is_overlap, to_minutes
from sample_data import BOOKINGS, RESOURCES


def req(**kw):
    base = {"resource_id": "R01", "date": "12 Oct", "start": "10:00",
            "end": "13:00", "attendees": 45, "needs": ["projector"]}
    base.update(kw)
    return base


def types(result):
    return [c["type"] for c in result["conflicts"]]


# TC-E3-01 normal: B002 vs B001 is flagged, with reference to B001
def test_tc_e3_01_b002_conflicts_with_b001():
    result = find_conflicts(req(booking_id="B002"), BOOKINGS, RESOURCES)
    assert result["status"] == "CONFLICT"
    assert result["conflicts"][0]["type"] == "TIME"
    assert result["conflicts"][0]["booking_id"] == "B001"


def test_tc_e3_01_non_overlapping_not_flagged():
    # B003-style request: Lab 2, 14:00-16:00, nothing confirmed there
    result = find_conflicts(req(resource_id="R02", start="14:00", end="16:00",
                                attendees=35), BOOKINGS, RESOURCES)
    assert result["status"] == "OK"


# TC-E3-02 boundary: adjacent / equal / partial / contained intervals
def test_tc_e3_02_adjacent_is_not_conflict():
    assert is_overlap(600, 780, 780, 900) is False
    result = find_conflicts(req(start="13:00", end="15:00"), BOOKINGS, RESOURCES)
    assert result["status"] == "OK"


@pytest.mark.parametrize("s,e", [
    ("10:00", "13:00"),   # equal
    ("12:00", "14:00"),   # partial
    ("11:00", "12:00"),   # contained
    ("09:00", "14:00"),   # containing
])
def test_tc_e3_02_overlap_cases(s, e):
    result = find_conflicts(req(start=s, end=e), BOOKINGS, RESOURCES)
    assert "TIME" in types(result)


def test_different_date_or_resource_not_flagged():
    assert find_conflicts(req(date="13 Oct"), BOOKINGS, RESOURCES)["status"] == "OK"
    assert find_conflicts(req(resource_id="R02"), BOOKINGS, RESOURCES)["status"] == "OK"


# TC-E3-03 failure: capacity and equipment mismatch
def test_tc_e3_03_capacity_conflict():
    result = find_conflicts(req(resource_id="R03", attendees=130, needs=[]),
                            BOOKINGS, RESOURCES)
    assert "CAPACITY" in types(result)


def test_tc_e3_03_equipment_conflict():
    result = find_conflicts(req(resource_id="R01", date="14 Oct",
                                needs=["microphone"]), BOOKINGS, RESOURCES)
    assert types(result) == ["EQUIPMENT"]


# invalid input
def test_end_before_start_rejected():
    with pytest.raises(ValueError):
        find_conflicts(req(start="13:00", end="10:00"), BOOKINGS, RESOURCES)


def test_bad_time_rejected():
    with pytest.raises(ValueError):
        to_minutes("25:99")


# TC-E3-04 performance: 500+ bookings checked within 2 seconds
def test_tc_e3_04_performance_500_bookings():
    many = [{"booking_id": f"X{i}", "event": "e", "date": "12 Oct",
             "start": f"{(i % 12) + 6:02d}:00", "end": f"{(i % 12) + 6:02d}:30",
             "resource_id": "R01", "attendees": 10, "status": "Confirmed"}
            for i in range(600)]
    t0 = time.perf_counter()
    find_conflicts(req(start="10:00", end="11:00"), many, RESOURCES)
    assert time.perf_counter() - t0 < 2
