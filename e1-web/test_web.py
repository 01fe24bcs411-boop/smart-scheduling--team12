import pytest
import app as webapp
import auth
import database as db
import validation


def make_client(tmp_path):
    flask_app = webapp.create_app(str(tmp_path / "web.db"), seed_demo=False)
    conn = db.connect(str(tmp_path / "web.db"))
    auth.register(conn, "Admin", "admin@t.test", "secret1", "Admin")
    auth.register(conn, "Org One", "o1@t.test", "secret1", "Organizer")
    auth.register(conn, "Org Two", "o2@t.test", "secret1", "Organizer")
    conn.close()
    return flask_app


def login(client, email, password="secret1"):
    return client.post("/login", json={"email": email, "password": password})


FORM = {"eventName": "TCS Placement Drive", "resourceId": "R01", "date": "2026-10-12",
        "start": "10:00", "end": "13:00", "attendees": 45, "needs": ["projector"]}


def full_booking(client, **over):
    r = client.post("/api/requests", json={**FORM, **over})
    assert r.status_code == 200, r.get_json()
    rid = r.get_json()["requestId"]
    return rid, client.post("/api/check", json={"requestId": rid}).get_json()


# ---- passwords ----
def test_password_is_hashed_and_verified():
    stored = auth.hash_password("secret1")
    assert "secret1" not in stored and auth.verify_password("secret1", stored)
    assert not auth.verify_password("wrong", stored)


def test_wrong_password_rejected(tmp_path):
    c = make_client(tmp_path).test_client()
    assert login(c, "o1@t.test", "nope").status_code == 401
    assert c.get("/api/schedule").status_code == 401


# TC-E1-01: valid request -> confirmation, then cancel frees the slot
def test_tc_e1_01_create_confirm_and_cancel(tmp_path):
    c = make_client(tmp_path).test_client()
    login(c, "o1@t.test")
    rid, check = full_booking(c)
    assert check["status"] == "OK"
    done = c.post("/api/confirm", json={"request_id": rid})
    assert done.status_code == 200 and done.get_json()["status"] == "CONFIRMED"
    booking_id = done.get_json()["booking_id"]
    assert c.post("/api/cancel", json={"booking_id": booking_id}).get_json()["status"] == "CANCELLED"
    _, again = full_booking(c)
    assert again["status"] == "OK"


# TC-E1-02: invalid input -> clear messages, nothing created
def test_tc_e1_02_validation_messages(tmp_path):
    c = make_client(tmp_path).test_client()
    login(c, "o1@t.test")
    r = c.post("/api/requests", json={**FORM, "start": "13:00", "end": "10:00", "attendees": "abc"})
    assert r.status_code == 400
    errors = r.get_json()["errors"]
    assert "End time must be after start time" in errors["end"] and "attendees" in errors
    assert db.connect(str(tmp_path / "web.db")).execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_validation_unit():
    clean, errors = validation.validate_event_form(FORM)
    assert errors == {} and clean["needs"] == ["projector"]
    _, errors = validation.validate_event_form({**FORM, "date": "12/10/2026", "start": "9:00"})
    assert "date" in errors and "start" in errors


# TC-E1-03: role check - Organizer cannot edit resources
def test_tc_e1_03_organizer_cannot_add_resource(tmp_path):
    c = make_client(tmp_path).test_client()
    login(c, "o1@t.test")
    r = c.post("/api/resources", json={"name": "Lab 3", "type": "Lab", "capacity": 40})
    assert r.status_code == 403


def test_admin_adds_resource_and_cannot_book(tmp_path):
    c = make_client(tmp_path).test_client()
    login(c, "admin@t.test")
    r = c.post("/api/resources", json={"name": "Computer Lab 3", "type": "Lab", "capacity": 40,
                                       "facilities": "projector, computers"})
    assert r.status_code == 200 and r.get_json()["resource_id"] == "R05"     # TC-E2-01 via web
    assert c.post("/api/requests", json=FORM).status_code == 403
    assert c.post("/api/resources", json={"name": "", "type": "Lab", "capacity": 0}).status_code == 400


# TC-E1-04: schedule filter
def test_tc_e1_04_schedule_filter(tmp_path):
    flask_app = make_client(tmp_path)
    c = flask_app.test_client()
    login(c, "o1@t.test")
    for resource in ("R01", "R02"):
        rid, _ = full_booking(c, resourceId=resource)
        c.post("/api/confirm", json={"request_id": rid})
    login(c, "admin@t.test")
    assert len(c.get("/api/schedule").get_json()) == 2
    only = c.get("/api/schedule?resource_id=R01").get_json()
    assert len(only) == 1 and only[0]["resource_id"] == "R01"
    assert c.get("/api/schedule?date=2030-01-01").get_json() == []


# TC-API-01: missing field
def test_tc_api_01_missing_field_400(tmp_path):
    c = make_client(tmp_path).test_client()
    login(c, "o1@t.test")
    bad = {k: v for k, v in FORM.items() if k != "date"}
    r = c.post("/api/requests", json=bad)
    assert r.status_code == 400 and "date" in r.get_json()["errors"]
    assert c.post("/api/requests", json={**FORM, "resourceId": "R99"}).status_code == 400


# conflict -> alternatives -> accept alternative (E1 -> E3 -> E5 -> E4 -> E2)
def test_conflict_shows_alternatives_and_accepting_one_works(tmp_path):
    flask_app = make_client(tmp_path)
    one, two = flask_app.test_client(), flask_app.test_client()
    login(one, "o1@t.test"); login(two, "o2@t.test")
    rid1, check1 = full_booking(one, eventName="AI Hackathon", attendees=55)
    assert one.post("/api/confirm", json={"request_id": rid1}).status_code == 200
    rid2, check2 = full_booking(two)
    assert check2["status"] == "CONFLICT" and check2["conflicts"][0]["type"] == "TIME"
    assert check2["alternatives"][0]["resource_id"] == "R02"
    # direct confirm of the clashing room is refused (409) and alternatives come back
    refused = two.post("/api/confirm", json={"request_id": rid2})
    assert refused.status_code == 409 and refused.get_json()["alternatives"]
    accepted = two.post("/api/confirm", json={"request_id": rid2,
                                              "choice": check2["alternatives"][0]})
    assert accepted.status_code == 200 and accepted.get_json()["resource_id"] == "R02"


def test_cannot_use_or_cancel_someone_elses_request(tmp_path):
    flask_app = make_client(tmp_path)
    one, two = flask_app.test_client(), flask_app.test_client()
    login(one, "o1@t.test"); login(two, "o2@t.test")
    rid, _ = full_booking(one)
    assert two.post("/api/check", json={"requestId": rid}).status_code == 403
    done = one.post("/api/confirm", json={"request_id": rid}).get_json()
    assert two.post("/api/cancel", json={"booking_id": done["booking_id"]}).status_code == 403
