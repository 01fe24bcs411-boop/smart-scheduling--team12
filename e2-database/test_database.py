import sqlite3
import threading
import pytest
import database as db


def make_db(path=":memory:"):
    conn = db.connect(path)
    db.init_db(conn)
    db.seed_sample(conn)
    return conn


def book(conn, rid="R01", date="12 Oct", start="10:00", end="13:00", attendance=55,
         title="AI Hackathon", equipment=None):
    ev = db.create_event(conn, None, title, "Event", attendance)
    return db.commit_booking(conn, ev, rid, date, start, end, equipment)


def test_schema_has_six_tables():
    conn = make_db()
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "events", "resources", "equipment", "bookings", "booking_equipment"} <= names


# TC-E2-01: admin adds a new lab and it appears
def test_tc_e2_01_new_lab_appears():
    conn = make_db()
    rid = db.next_resource_id(conn)
    db.add_resource(conn, rid, "Computer Lab 3", "Lab", 40, ["Computers", "Projector"])
    resources = db.get_resources(conn)
    assert rid == "R05" and resources["R05"]["name"] == "Computer Lab 3"
    assert resources["R05"]["facilities"] == {"computers", "projector"}


# TC-E2-04: availability
def test_tc_e2_04_availability_busy_then_free():
    conn = make_db()
    assert db.is_available(conn, "R01", "12 Oct", "10:00", "13:00")
    assert book(conn)["status"] == "COMMITTED"
    assert not db.is_available(conn, "R01", "12 Oct", "10:00", "13:00")
    assert not db.is_available(conn, "R01", "12 Oct", "12:00", "14:00")   # partial overlap
    assert db.is_available(conn, "R01", "12 Oct", "13:00", "15:00")       # adjacent
    assert db.is_available(conn, "R02", "12 Oct", "10:00", "13:00")       # other room


# TC-E2-02: duplicate slot rejected, one row only
def test_tc_e2_02_duplicate_rejected_by_commit():
    conn = make_db()
    assert book(conn)["status"] == "COMMITTED"
    second = book(conn, title="TCS Placement Drive", attendance=45)
    assert second["status"] == "ROLLED BACK"
    assert conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 1


def test_tc_e2_02_unique_constraint_blocks_raw_insert():
    conn = make_db()
    book(conn)
    ev = db.create_event(conn, None, "Other", "Event", 10)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO bookings(event_id,resource_id,date,start_time,end_time) "
                     "VALUES (?,?,?,?,?)", (ev, "R01", "12 Oct", "10:00", "11:00"))


# TC-E2-03: failure mid-commit -> rollback, nothing saved
def test_tc_e2_03_rollback_when_equipment_short():
    conn = make_db()
    result = book(conn, equipment={"microphone": 5})        # only 2 in stock
    assert result["status"] == "ROLLED BACK"
    assert conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM booking_equipment").fetchone()[0] == 0
    assert db.is_available(conn, "R01", "12 Oct", "10:00", "13:00")


def test_rollback_unknown_resource():
    conn = make_db()
    assert book(conn, rid="R99")["status"] == "ROLLED BACK"


def test_equipment_stock_counts_across_overlapping_bookings():
    conn = make_db()
    assert book(conn, rid="R01", equipment={"microphone": 2})["status"] == "COMMITTED"
    assert book(conn, rid="R02", equipment={"microphone": 1})["status"] == "ROLLED BACK"


def test_free_resources_filters_capacity_and_facilities():
    conn = make_db()
    book(conn)                                                    # R01 busy
    free = db.free_resources(conn, "12 Oct", "10:00", "13:00", 45, ["projector"])
    assert [r["resource_id"] for r in free] == ["R02", "R03", "R04"]
    free = db.free_resources(conn, "12 Oct", "10:00", "13:00", 45, ["microphone"])
    assert [r["resource_id"] for r in free] == ["R03"]


def test_cancel_frees_slot_and_marks_event():
    conn = make_db()
    bid = book(conn)["booking_id"]
    assert db.cancel_booking(conn, bid)["status"] == "CANCELLED"
    assert db.is_available(conn, "R01", "12 Oct", "10:00", "13:00")
    assert conn.execute("SELECT status FROM events").fetchone()[0] == "Cancelled"
    assert book(conn, title="TCS Placement Drive")["status"] == "COMMITTED"   # slot reusable
    assert db.cancel_booking(conn, 999)["status"] == "NOT FOUND"


def test_get_bookings_shape_for_e3():
    conn = make_db()
    book(conn)
    b = db.get_bookings(conn, date="12 Oct")[0]
    assert {"booking_id", "event", "date", "start", "end", "resource_id", "attendees", "status"} <= set(b)


# concurrency safety of E2 on its own (two separate connections, same slot)
def test_two_connections_same_slot_only_one_commits(tmp_path):
    path = str(tmp_path / "t.db")
    setup = make_db(path)
    ev1 = db.create_event(setup, None, "A", "E", 10)
    ev2 = db.create_event(setup, None, "B", "E", 10)
    results = []
    barrier = threading.Barrier(2)

    def worker(ev):
        conn = db.connect(path)
        barrier.wait()
        results.append(db.commit_booking(conn, ev, "R01", "12 Oct", "10:00", "13:00")["status"])
        conn.close()

    threads = [threading.Thread(target=worker, args=(e,)) for e in (ev1, ev2)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert sorted(results) == ["COMMITTED", "ROLLED BACK"]
    assert setup.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 1


def test_backup_copies_data(tmp_path):
    conn = make_db()
    book(conn)
    dest = db.backup(conn, str(tmp_path / "backup.db"))
    copy = db.connect(dest)
    assert copy.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 1
    assert len(db.get_resources(copy)) == 4


# TC-E2-05: boundary - capacity exactly equals attendance, facility present
def test_tc_e2_05_suitable_when_capacity_exactly_equal():
    conn = make_db()
    lab2 = db.get_resources(conn)["R02"]                       # capacity 50, projector
    assert db.check_resource_suitability(lab2, 50, ["projector"]) == {
        "suitable": True, "reason": "Capacity and facilities fit"}


# TC-E2-06: failure - capacity too small or equipment missing
def test_tc_e2_06_unsuitable_with_reason():
    conn = make_db()
    lab2 = db.get_resources(conn)["R02"]
    small = db.check_resource_suitability(lab2, 51, [])
    assert small["suitable"] is False and "Capacity 50" in small["reason"]
    missing = db.check_resource_suitability(lab2, 10, ["microphone"])
    assert missing == {"suitable": False, "reason": "Missing: microphone"}


def test_event_status_and_list_events():
    conn = make_db()
    org = db.add_user(conn, "Org", "o@x.test", "hash", "Organizer")
    e1 = db.create_event(conn, org, "AI Hackathon", "Event", 55)
    e2 = db.create_event(conn, org, "TCS Placement Drive", "Event", 45)
    assert db.commit_booking(conn, e1, "R01", "12 Oct", "10:00", "13:00")["status"] == "COMMITTED"
    db.set_event_status(conn, e2, "Conflict Detected")
    db.set_event_status(conn, e1, "Rejected")              # a Confirmed event is never changed
    rows = {r["title"]: r for r in db.list_events(conn)}
    assert rows["AI Hackathon"]["status"] == "Confirmed" and rows["AI Hackathon"]["resource_id"] == "R01"
    assert rows["TCS Placement Drive"]["status"] == "Conflict Detected"
    assert rows["TCS Placement Drive"]["resource_id"] is None
    assert db.list_events(conn, organizer_id=999) == []
