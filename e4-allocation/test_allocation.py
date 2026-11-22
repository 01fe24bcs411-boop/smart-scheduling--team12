import threading
import allocation as al
import database as db


def setup_db(tmp_path):
    path = str(tmp_path / "e4.db")
    conn = db.connect(path)
    db.init_db(conn)
    db.seed_sample(conn)
    return path, conn


def request(conn, title="Event", attendees=45, needs=("projector",), resource_id=None,
            start="10:00", end="13:00", priority=1):
    ev = db.create_event(conn, None, title, "Event", attendees, priority)
    r = {"event_id": ev, "date": "12 Oct", "start": start, "end": end,
         "attendees": attendees, "needs": list(needs), "priority": priority}
    if resource_id:
        r["resource_id"] = resource_id
    return r


def test_best_fit_picks_smallest_room_that_fits():
    free = [{"resource_id": "R01", "capacity": 60}, {"resource_id": "R02", "capacity": 50},
            {"resource_id": "R03", "capacity": 120}]
    assert al.best_fit(free)["resource_id"] == "R02"
    assert al.best_fit([]) is None


# TC-E4-01: normal best-fit allocation
def test_tc_e4_01_best_fit_allocates_seminar_hall_for_microphone(tmp_path):
    path, conn = setup_db(tmp_path)
    result = al.allocate(path, request(conn, "Club event", 40, ["projector", "microphone"]))
    assert result["status"] == "CONFIRMED" and result["resource_id"] == "R03"


def test_best_fit_without_special_need_picks_lab2(tmp_path):
    path, conn = setup_db(tmp_path)
    result = al.allocate(path, request(conn, "Seminar", 45, ["projector"]))
    assert result["resource_id"] == "R02"            # capacity 50 is the smallest that fits 45


def test_specific_room_free_is_confirmed(tmp_path):
    path, conn = setup_db(tmp_path)
    result = al.allocate(path, request(conn, "AI Hackathon", 55, ["projector"], "R01"))
    assert result["status"] == "CONFIRMED" and result["resource_id"] == "R01"


def test_no_suitable_resource_rejected(tmp_path):
    path, conn = setup_db(tmp_path)
    result = al.allocate(path, request(conn, "Huge", 500, []))
    assert result["status"] == "REJECTED"


def test_taken_slot_rejected_with_reason(tmp_path):
    path, conn = setup_db(tmp_path)
    assert al.allocate(path, request(conn, "A", 55, ["projector"], "R01"))["status"] == "CONFIRMED"
    second = al.allocate(path, request(conn, "B", 45, ["projector"], "R01"))
    assert second["status"] == "REJECTED" and second["conflicts"][0]["type"] == "TIME"


def test_bad_time_rejected(tmp_path):
    path, conn = setup_db(tmp_path)
    assert al.allocate(path, request(conn, "Bad", 10, [], "R01", start="13:00", end="10:00"))["status"] == "REJECTED"


# TC-E4-02: two organizers confirm the same slot at the same time
def test_tc_e4_02_concurrent_requests_exactly_one_wins(tmp_path):
    path, conn = setup_db(tmp_path)
    r1 = request(conn, "Organizer 1", 45, ["projector"], "R01")
    r2 = request(conn, "Organizer 2", 45, ["projector"], "R01")
    results, barrier = [], threading.Barrier(2)

    def worker(req):
        barrier.wait()
        results.append(al.allocate(path, req)["status"])

    threads = [threading.Thread(target=worker, args=(r,)) for r in (r1, r2)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert sorted(results) == ["CONFIRMED", "REJECTED"]
    assert conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 1


# TC-E4-03: a lock that is never released times out; the next request then works
def test_tc_e4_03_lock_timeout_then_recovery(tmp_path):
    path, conn = setup_db(tmp_path)
    al._LOCK.acquire()                                  # simulate a stuck holder
    try:
        stuck = al.allocate(path, request(conn, "A", 45, ["projector"]), lock_timeout=0.2)
        assert stuck["status"] == "REJECTED" and "Lock timeout" in stuck["reason"]
    finally:
        al._LOCK.release()
    assert al.allocate(path, request(conn, "A2", 45, ["projector"]))["status"] == "CONFIRMED"


def test_priority_order_and_queue(tmp_path):
    path, conn = setup_db(tmp_path)
    low = request(conn, "Low priority", 45, ["projector"], "R01", priority=1)
    high = request(conn, "High priority", 45, ["projector"], "R01", priority=3)
    assert [r["priority"] for r in al.sort_by_priority([low, high])] == [3, 1]
    outcome = {r["priority"]: res["status"] for r, res in al.process_queue(path, [low, high])}
    assert outcome == {3: "CONFIRMED", 1: "REJECTED"}


def test_equal_priority_keeps_arrival_order():
    a, b, c = ({"priority": 2, "n": i} for i in range(3))
    assert [r["n"] for r in al.sort_by_priority([a, b, c])] == [0, 1, 2]
