import alternatives as alt
import database as db


def make_db():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.seed_sample(conn)
    return conn


def book(conn, rid, start="10:00", end="13:00", title="Busy"):
    ev = db.create_event(conn, None, title, "Event", 10)
    assert db.commit_booking(conn, ev, rid, "12 Oct", start, end)["status"] == "COMMITTED"


def req(**kw):
    base = {"resource_id": "R01", "date": "12 Oct", "start": "10:00", "end": "13:00",
            "attendees": 45, "needs": ["projector"]}
    base.update(kw)
    return base


# TC-E5-01: Lab 1 busy -> Lab 2 suggested for the same slot
def test_tc_e5_01_lab2_suggested_when_lab1_busy():
    conn = make_db()
    book(conn, "R01", title="AI Hackathon")
    options = alt.suggest_alternatives(conn, req())
    assert options[0]["kind"] == "ROOM" and options[0]["resource_id"] == "R02"
    assert [o["resource_id"] for o in options] == ["R02", "R03", "R04"]   # ranked by spare seats
    assert all(o["start"] == "10:00" and o["end"] == "13:00" for o in options)


def test_original_room_never_suggested():
    conn = make_db()
    assert "R01" not in [o["resource_id"] for o in alt.suggest_alternatives(conn, req())]


# TC-E5-02: every suitable room busy -> nearest free slot, ranked by closeness
def test_tc_e5_02_nearest_slot_when_all_rooms_busy():
    conn = make_db()
    for rid in ("R01", "R02", "R03", "R04"):
        book(conn, rid)
    options = alt.suggest_alternatives(conn, req())
    assert options[0]["kind"] == "SLOT"
    assert (options[0]["resource_id"], options[0]["start"], options[0]["end"]) == ("R02", "13:00", "16:00")
    distances = [abs(alt.to_minutes(o["start"]) - alt.to_minutes("10:00")) for o in options]
    assert distances == sorted(distances)


# TC-E5-03: nothing feasible -> empty list (E1 shows a message)
def test_tc_e5_03_no_feasible_alternative():
    conn = make_db()
    assert alt.suggest_alternatives(conn, req(attendees=500)) == []
    assert alt.suggest_alternatives(conn, req(needs=["stage", "microphone"])) == []


def test_equipment_need_limits_rooms():
    conn = make_db()
    book(conn, "R03")
    assert alt.suggest_alternatives(conn, req(resource_id="R03", needs=["microphone"]))[0]["kind"] == "SLOT"


def test_limit_respected():
    conn = make_db()
    for rid in ("R01", "R02", "R03", "R04"):
        book(conn, rid)
    assert len(alt.suggest_alternatives(conn, req(), limit=2)) == 2
