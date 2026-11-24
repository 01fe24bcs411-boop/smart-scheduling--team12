"""Section 4.16 state diagram checked through the real E1 web API (run inside e1-web)."""
from test_web import make_client, login, full_booking, FORM


def info(client, rid):
    r = client.get(f"/api/state/{rid}")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def path(client, rid):
    return [h["to"] for h in info(client, rid)["history"]]


# TC-ST-E1-01: normal booking, then cancel: Requested > Validating > Allocating > Confirmed > Cancelled > End
def test_tc_st_e1_01_normal_then_cancel(tmp_path):
    c = make_client(tmp_path).test_client(); login(c, "o1@t.test")
    rid, check = full_booking(c)
    assert check["status"] == "OK" and info(c, rid)["state"] == "Allocating"
    done = c.post("/api/confirm", json={"request_id": rid})
    assert done.status_code == 200 and info(c, rid)["state"] == "Confirmed"
    c.post("/api/cancel", json={"booking_id": done.get_json()["booking_id"]})
    assert path(c, rid) == ["Requested", "Validating", "Allocating", "Confirmed", "Cancelled", "End"]


# TC-ST-E1-02: invalid input keeps the request in Requested
def test_tc_st_e1_02_invalid_input_stays_requested(tmp_path):
    c = make_client(tmp_path).test_client(); login(c, "o1@t.test")
    r = c.post("/api/requests", json={**FORM, "start": "13:00", "end": "10:00"})
    assert r.status_code == 400 and r.get_json()["state"] == "Requested"


# TC-ST-E1-03: conflict -> alternative suggested -> accepted -> confirmed
def test_tc_st_e1_03_conflict_alternative_accepted(tmp_path):
    app = make_client(tmp_path)
    one, two = app.test_client(), app.test_client()
    login(one, "o1@t.test"); login(two, "o2@t.test")
    rid1, _ = full_booking(one, eventName="AI Hackathon", attendees=55)
    assert one.post("/api/confirm", json={"request_id": rid1}).status_code == 200
    rid2, check = full_booking(two)
    assert check["status"] == "CONFLICT" and info(two, rid2)["state"] == "Alternative Suggested"
    ok = two.post("/api/confirm", json={"request_id": rid2, "choice": check["alternatives"][0]})
    assert ok.status_code == 200
    assert path(two, rid2) == ["Requested", "Validating", "Conflict Detected", "Alternative Suggested",
                               "Validating", "Allocating", "Confirmed"]


# TC-ST-E1-04: organizer insists on the clashing slot -> 409 and Rejected; later picks an alternative
def test_tc_st_e1_04_declined_then_resubmitted(tmp_path):
    app = make_client(tmp_path)
    one, two = app.test_client(), app.test_client()
    login(one, "o1@t.test"); login(two, "o2@t.test")
    rid1, _ = full_booking(one, eventName="AI Hackathon", attendees=55)
    one.post("/api/confirm", json={"request_id": rid1})
    rid2, check = full_booking(two)
    assert two.post("/api/confirm", json={"request_id": rid2}).status_code == 409
    assert info(two, rid2)["state"] == "Rejected"
    ok = two.post("/api/confirm", json={"request_id": rid2, "choice": check["alternatives"][0]})
    assert ok.status_code == 200 and info(two, rid2)["state"] == "Confirmed"
    assert "Rejected" in path(two, rid2)


# TC-ST-E1-05: only the owner or an Admin can read a request's state
def test_tc_st_e1_05_state_access(tmp_path):
    app = make_client(tmp_path)
    one, two, admin = app.test_client(), app.test_client(), app.test_client()
    login(one, "o1@t.test"); login(two, "o2@t.test"); login(admin, "admin@t.test")
    rid, _ = full_booking(one)
    assert two.get(f"/api/state/{rid}").status_code == 403
    assert admin.get(f"/api/state/{rid}").status_code == 200
    assert one.get("/api/state/9999").status_code == 404
