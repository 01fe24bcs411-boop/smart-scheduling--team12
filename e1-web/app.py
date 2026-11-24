"""E1 - Event Creation & Web Interface (Ganesh).

Flask web app + JSON API following Sprint 1 section 4.19:
  POST /api/requests    validate and register an event request
  POST /api/check       E3 conflict check (+ E5 alternatives when there is a clash)
  POST /api/alternatives  E5 ranked alternatives for a request
  POST /api/confirm     E4 allocation and E2 commit (200 CONFIRMED / 409 REJECTED)
  POST /api/cancel      cancel own booking
  POST /api/resources   Admin only
  GET  /api/schedule    filter by date / resource_id
  GET  /api/state/<id>  request state + history (Sprint 1 section 4.16 state diagram)
In this sprint the engines are called in-process (plain function calls), not over HTTP.
"""
import os
import sys
from functools import wraps

HERE = os.path.dirname(os.path.abspath(__file__))
for _f in ("e2-database", "e3-conflict", "e4-allocation", "e5-alternatives", "state-machine"):
    sys.path.insert(0, os.path.join(HERE, "..", _f))

from flask import Flask, g, jsonify, redirect, render_template_string, request, session

import auth
import database as db
import validation
from alternatives import suggest_alternatives
from allocation import allocate
from conflict_detection import find_conflicts
import booking_state as bs

PAGE = """<!doctype html><title>Smart Scheduling</title>
<style>body{font-family:sans-serif;max-width:820px;margin:20px auto}input,select{margin:3px}
table{border-collapse:collapse}td,th{border:1px solid #999;padding:4px 8px}.err{color:#b00}.ok{color:#080}</style>
<h2>CS Department Smart Scheduling</h2>
{% if not user %}
<form method="post" action="/login"><h3>Login</h3>
<input name="email" placeholder="email"><input name="password" type="password" placeholder="password">
<button>Login</button></form><p class="err">{{ error or '' }}</p>
{% else %}
<p>Logged in as <b>{{ user.name }}</b> ({{ user.role }}) | <a href="/logout">Logout</a></p>
{% if user.role == 'Organizer' %}
<h3>Book an event</h3>
<form id="f">
<input name="eventName" placeholder="Event name"><input name="resourceId" placeholder="Resource e.g. R01">
<input name="date" type="date"><input name="start" type="time"><input name="end" type="time">
<input name="attendees" type="number" placeholder="Attendees"><input name="needs" placeholder="needs: projector,microphone">
<button>Check and book</button></form>
{% else %}
<h3>Add resource (Admin)</h3>
<form id="r"><input name="name" placeholder="Name"><input name="type" placeholder="Lab/Hall">
<input name="capacity" type="number" placeholder="Capacity"><input name="facilities" placeholder="projector,computers">
<button>Add</button></form>
{% endif %}
<pre id="out"></pre>
<h3>Requests and their status</h3><table id="req"><tr><th>ID</th><th>Event</th><th>By</th><th>Room</th><th>Date</th><th>Time</th><th>Status</th></tr></table>
<h3>Schedule (confirmed bookings only)</h3><table id="sch"><tr><th>ID</th><th>Event</th><th>Date</th><th>Time</th><th>Resource</th><th>Status</th></tr></table>
<script>
const out=document.getElementById('out');
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return [r.status,await r.json()]}
async function load(){const r=await fetch('/api/schedule');const rows=await r.json();
 const t=document.getElementById('sch');t.innerHTML=t.rows[0].outerHTML;
 rows.forEach(b=>{t.insertAdjacentHTML('beforeend',`<tr><td>${b.booking_id}</td><td>${b.event}</td><td>${b.date}</td><td>${b.start}-${b.end}</td><td>${b.resource_id}</td><td>${b.status}</td></tr>`)})}
async function loadReq(){const r=await fetch('/api/event-requests');const rows=await r.json();
 const t=document.getElementById('req');t.innerHTML=t.rows[0].outerHTML;
 rows.forEach(b=>{const c=(b.status=='Conflict Detected'||b.status=='Rejected')?'err':(b.status=='Confirmed'?'ok':'');
  t.insertAdjacentHTML('beforeend',`<tr><td>${b.event_id}</td><td>${b.title}</td><td>${b.organizer||''}</td><td>${b.resource_id||'-'}</td><td>${b.date||'-'}</td><td>${b.start?b.start+'-'+b.end:'-'}</td><td class="${c}">${b.status}</td></tr>`)})}
function showAlternatives(rid,alts){
 out.innerHTML='<p class="err">Conflict detected. Pick an available alternative:</p>';
 if(!alts||!alts.length){out.insertAdjacentHTML('beforeend','<p>No alternatives available.</p>');return}
 alts.forEach(a=>{
  const b=document.createElement('button');
  b.textContent=`Book ${a.resource_id} on ${a.date} ${a.start}-${a.end}`;
  b.style.margin='4px';
  b.onclick=async()=>{
   const [s,k]=await post('/api/confirm',{request_id:rid,choice:a});
   out.textContent=JSON.stringify(k,null,1);
   load();loadReq()};
  out.appendChild(b);
 })}
const f=document.getElementById('f');
if(f)f.onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(f));
 let [s,r]=await post('/api/requests',d);if(s!=200){out.textContent='Fix the form:\\n'+JSON.stringify(r.errors,null,1);return}
 [s,c]=await post('/api/check',{requestId:r.requestId});
 if(c.status=='OK'){[s,k]=await post('/api/confirm',{request_id:r.requestId});out.textContent=JSON.stringify(k,null,1);}
 else{showAlternatives(r.requestId,c.alternatives);}
 load();loadReq()};
const rf=document.getElementById('r');
if(rf)rf.onsubmit=async e=>{e.preventDefault();const [s,r]=await post('/api/resources',Object.fromEntries(new FormData(rf)));out.textContent=JSON.stringify(r,null,1)};
load();loadReq();
</script>{% endif %}"""


def create_app(db_path=None, seed_demo=True):
    db_path = db_path or os.path.join(HERE, "scheduler.db")
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
    app.config["DB_PATH"] = db_path
    pending = {}            # requestId -> clean request (lost on restart; fine for Sprint 2)
    states = {}             # requestId -> BookingRequestState (section 4.16; in memory like pending)
    booking_event = {}      # booking_id -> requestId (to move Confirmed -> Cancelled)

    def go(st, *events):
        for e in events:
            st.fire(e)
        return st.state

    def to_allocating(st):
        # bring a request that is about to be committed to 'Allocating' along legal transitions only
        if st.state == bs.REJECTED:
            go(st, "resubmit")
        if st.state == bs.REQUESTED:
            go(st, "input_valid")
        if st.state == bs.VALIDATING:
            go(st, "no_conflict")

    def after_reject(st, result, alternatives):
        # E4 refused the booking: Validating/Allocating -> Conflict Detected -> Alternative Suggested / Rejected
        if st.state == bs.REJECTED:
            return                      # organizer already declined; stays Rejected
        reason = str(result.get("reason", ""))
        if st.state == bs.VALIDATING:
            if result.get("conflicts"):
                go(st, "conflict")         # E3 found a clash at re-check
            else:
                go(st, "no_conflict")      # E3 passed; failure happened while allocating
        if st.state == bs.ALLOCATING:
            if reason.startswith("Lock timeout") or reason == "Slot already taken":
                go(st, "lock_lost")        # E4 lock timeout / E2 UNIQUE: another request won the slot
            else:
                go(st, "db_failure")       # E2 rolled back (e.g. equipment short): nothing saved, retry
        if st.state == bs.CONFLICT_DETECTED:
            go(st, "alternative_found" if alternatives else "no_alternative")

    boot = db.connect(db_path)
    db.init_db(boot)
    if not db.get_resources(boot):
        db.seed_sample(boot)
    if seed_demo and db.count_users(boot) == 0:        # demo accounts - change for real use
        auth.register(boot, "Demo Admin", "admin@campus.test", "admin123", "Admin")
        auth.register(boot, "Demo Organizer", "organizer@campus.test", "organizer123", "Organizer")
    boot.close()

    def conn():
        if "db" not in g:
            g.db = db.connect(app.config["DB_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        c = g.pop("db", None)
        if c is not None:
            c.close()

    def needs(action):
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                if "user_id" not in session:
                    return jsonify(error="Login required"), 401
                if not auth.can(session["role"], action):
                    return jsonify(error="Access denied for your role"), 403
                return fn(*a, **kw)
            return wrapper
        return deco

    def own_request(data):
        req = pending.get(data.get("requestId", data.get("request_id")))
        if req is None:
            return None, (jsonify(error="Unknown requestId"), 404)
        if req["organizer_id"] != session["user_id"]:
            return None, (jsonify(error="Not your request"), 403)
        return req, None

    # ---------------- pages ----------------
    @app.get("/")
    def index():
        user = None
        if "user_id" in session:
            user = {"name": session["name"], "role": session["role"]}
        return render_template_string(PAGE, user=user, error=request.args.get("error"))

    @app.post("/login")
    def login():
        data = request.get_json(silent=True) or request.form
        user = auth.login(conn(), data.get("email"), data.get("password"))
        if user is None:
            if request.is_json:
                return jsonify(error="Wrong email or password"), 401
            return redirect("/?error=Wrong+email+or+password")
        session.update(user_id=user["user_id"], role=user["role"], name=user["name"])
        return jsonify(ok=True, role=user["role"]) if request.is_json else redirect("/")

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect("/")

    # ---------------- API ----------------
    @app.post("/api/requests")
    @needs("create_event")
    def api_requests():
        form = request.get_json(silent=True) or {}
        clean, errors = validation.validate_event_form(form)
        resources = db.get_resources(conn())
        if "resourceId" not in errors and clean["resource_id"] not in resources:
            errors["resourceId"] = "Unknown resource"
        if errors:
            bad = bs.BookingRequestState()
            go(bad, "submit", "invalid_input")          # Requested --invalid_input--> Requested
            return jsonify(errors=errors, state=bad.state), 400
        event_id = db.create_event(conn(), session["user_id"], clean["title"], None,
                                   clean["attendees"], clean["priority"])
        clean["organizer_id"] = session["user_id"]
        pending[event_id] = clean
        st = bs.BookingRequestState(event_id)
        st.organizer_id = session["user_id"]
        go(st, "submit", "input_valid")                # Start -> Requested -> Validating
        states[event_id] = st
        candidates = [r["resource_id"] for r in resources.values()
                      if r["capacity"] >= clean["attendees"] and set(clean["needs"]) <= r["facilities"]]
        return jsonify(requestId=event_id, status="VALID", candidates=sorted(candidates))

    @app.post("/api/check")
    @needs("create_event")
    def api_check():
        req, err = own_request(request.get_json(silent=True) or {})
        if err:
            return err
        rid = (request.get_json(silent=True) or {}).get("requestId")
        st = states.get(rid)
        result = find_conflicts(req, db.get_bookings(conn(), date=req["date"]), db.get_resources(conn()))
        if result["status"] == "CONFLICT":
            db.set_event_status(conn(), rid, "Conflict Detected")
            result["alternatives"] = suggest_alternatives(conn(), req)
            if st is not None and st.state == bs.VALIDATING:
                go(st, "conflict", "alternative_found" if result["alternatives"] else "no_alternative")
                if st.state == bs.REJECTED:
                    db.set_event_status(conn(), rid, "Rejected")
        elif st is not None and st.state == bs.VALIDATING:
            go(st, "no_conflict")                         # Validating -> Allocating
        return jsonify(result)

    @app.post("/api/alternatives")
    @needs("create_event")
    def api_alternatives():
        data = request.get_json(silent=True) or {}
        req, err = own_request(data)
        if err:
            return err
        return jsonify(request_id=data.get("requestId", data.get("request_id")),
                       options=suggest_alternatives(conn(), req))

    @app.post("/api/confirm")
    @needs("create_event")
    def api_confirm():
        data = request.get_json(silent=True) or {}
        req, err = own_request(data)
        if err:
            return err
        choice = {k: v for k, v in (data.get("choice") or {}).items()
                  if k in ("resource_id", "date", "start", "end")}
        merged = {**req, **choice}
        _, errors = validation.validate_event_form({
            "eventName": merged["title"], "resourceId": merged["resource_id"], "date": merged["date"],
            "start": merged["start"], "end": merged["end"], "attendees": merged["attendees"]})
        if errors:
            return jsonify(errors=errors), 400
        merged["event_id"] = data.get("requestId", data.get("request_id"))
        st = states.get(merged["event_id"])
        if st is not None and st.state == bs.ALTERNATIVE_SUGGESTED:
            go(st, "accept" if choice else "decline")     # organizer picks an alternative, or insists on the clash
        result = allocate(app.config["DB_PATH"], merged)     # E4 always re-checks and commits under lock
        if result["status"] == "CONFIRMED":
            pending.pop(merged["event_id"], None)
            if st is not None:
                to_allocating(st)
                go(st, "commit_success")                  # Allocating -> Confirmed
                booking_event[result["booking_id"]] = merged["event_id"]
            return jsonify(result)
        result["alternatives"] = suggest_alternatives(conn(), merged)
        if st is not None:
            after_reject(st, result, result["alternatives"])
        if st is None or st.state == bs.REJECTED:
            shown = "Rejected"
        elif st.state == bs.REQUESTED:
            shown = "Requested"                           # rolled back, organizer retries
        else:
            shown = "Conflict Detected"
        db.set_event_status(conn(), merged["event_id"], shown)
        return jsonify(result), 409

    @app.post("/api/cancel")
    @needs("cancel_own_event")
    def api_cancel():
        booking_id = (request.get_json(silent=True) or {}).get("booking_id")
        owner = db.booking_organizer(conn(), booking_id)
        if owner is None:
            return jsonify(error="Booking not found"), 404
        if owner != session["user_id"]:
            return jsonify(error="You can cancel only your own events"), 403
        result = db.cancel_booking(conn(), booking_id)
        st = states.get(booking_event.pop(booking_id, None))
        if st is not None and st.state == bs.CONFIRMED and result.get("status") == "CANCELLED":
            go(st, "cancel", "close")                    # Confirmed -> Cancelled -> End
        return jsonify(result)

    @app.post("/api/resources")
    @needs("manage_resources")
    def api_add_resource():
        clean, errors = validation.validate_resource_form(request.get_json(silent=True) or {})
        if errors:
            return jsonify(errors=errors), 400
        rid = db.next_resource_id(conn())
        db.add_resource(conn(), rid, clean["name"], clean["type"], clean["capacity"], clean["facilities"])
        return jsonify(status="SAVED", resource_id=rid)

    @app.get("/api/resources")
    @needs("view_schedule")
    def api_list_resources():
        rows = [{**r, "facilities": sorted(r["facilities"])} for r in db.get_resources(conn()).values()]
        return jsonify(rows)

    @app.get("/api/event-requests")
    @needs("view_schedule")
    def api_event_requests():
        """Organizer sees own requests; Admin sees all. Status: Confirmed, Conflict Detected, Rejected..."""
        organizer = session["user_id"] if session["role"] == "Organizer" else None
        rows = db.list_events(conn(), organizer)
        for r in rows:
            req = pending.get(r["event_id"])
            if r["resource_id"] is None and req:        # not booked: show what was asked for
                r.update(resource_id=req["resource_id"], date=req["date"], start=req["start"], end=req["end"])
        return jsonify(rows)

    @app.get("/api/state/<int:request_id>")
    @needs("view_schedule")
    def api_state(request_id):
        """State (section 4.16) and full transition history of one request."""
        st = states.get(request_id)
        if st is None:
            return jsonify(error="No state recorded for this request"), 404
        if session["role"] != "Admin" and st.organizer_id != session["user_id"]:
            return jsonify(error="Not your request"), 403
        return jsonify(request_id=request_id, state=st.state, allowed_events=st.allowed_events(),
                       history=[{"time": t, "from": a, "event": e, "to": b} for t, a, e, b in st.history])

    @app.get("/api/schedule")
    @needs("view_schedule")
    def api_schedule():
        return jsonify(db.get_bookings(conn(), request.args.get("date"), request.args.get("resource_id")))

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
