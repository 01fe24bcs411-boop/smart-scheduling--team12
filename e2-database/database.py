"""E2 - Resource Checking & Data Consistency (Siddharth).

Design reference: Sprint 1 section 4.15 (ER diagram, tables), 4.18 (indexed
lookup, ACID transaction, UNIQUE(resource, date, start)) and 4.20 (backup).
Uses SQLite from the Python standard library - nothing to install.
"""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('Admin', 'Organizer'))
);
CREATE TABLE IF NOT EXISTS events (
    event_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    organizer_id        INTEGER REFERENCES users(user_id),
    title               TEXT NOT NULL,
    type                TEXT,
    expected_attendance INTEGER NOT NULL CHECK (expected_attendance > 0),
    priority            INTEGER NOT NULL DEFAULT 1,
    status              TEXT NOT NULL DEFAULT 'Requested'
);
CREATE TABLE IF NOT EXISTS resources (
    resource_id TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    capacity    INTEGER NOT NULL CHECK (capacity > 0),
    facilities  TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'Active'
);
CREATE TABLE IF NOT EXISTS equipment (
    equipment_id TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    total_qty    INTEGER NOT NULL CHECK (total_qty >= 0),
    status       TEXT NOT NULL DEFAULT 'Active'
);
CREATE TABLE IF NOT EXISTS bookings (
    booking_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(event_id),
    resource_id TEXT NOT NULL REFERENCES resources(resource_id),
    date        TEXT NOT NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'Confirmed',
    UNIQUE (resource_id, date, start_time)
);
CREATE TABLE IF NOT EXISTS booking_equipment (
    booking_id   INTEGER NOT NULL REFERENCES bookings(booking_id),
    equipment_id TEXT NOT NULL REFERENCES equipment(equipment_id),
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (booking_id, equipment_id)
);
CREATE INDEX IF NOT EXISTS idx_bookings_lookup
    ON bookings(resource_id, date, start_time);
"""

SAMPLE_RESOURCES = [  # Review 1 deck, slide 19
    ("R01", "Computer Lab 1", "Lab", 60, "computers,projector"),
    ("R02", "Computer Lab 2", "Lab", 50, "computers,projector"),
    ("R03", "Seminar Hall", "Hall", 120, "projector,microphone"),
    ("R04", "Auditorium", "Auditorium", 250, "audio,projector,stage"),
]
SAMPLE_EQUIPMENT = [("projector", "Projector", 4), ("microphone", "Microphone", 2),
                    ("display_board", "Display board", 2)]


class BookingError(Exception):
    pass


def connect(path=":memory:"):
    """New connection. Autocommit mode: transactions are explicit (BEGIN...)."""
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)


def seed_sample(conn):
    for rid, name, typ, cap, fac in SAMPLE_RESOURCES:
        conn.execute("INSERT OR IGNORE INTO resources VALUES (?,?,?,?,?, 'Active')",
                     (rid, name, typ, cap, fac))
    for eid, name, qty in SAMPLE_EQUIPMENT:
        conn.execute("INSERT OR IGNORE INTO equipment VALUES (?,?,?, 'Active')",
                     (eid, name, qty))


# ---------------- users / resources ----------------
def add_user(conn, name, email, password_hash, role):
    cur = conn.execute("INSERT INTO users(name,email,password_hash,role) VALUES (?,?,?,?)",
                       (name, email.lower(), password_hash, role))
    return cur.lastrowid


def get_user_by_email(conn, email):
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    return dict(row) if row else None


def count_users(conn):
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def next_resource_id(conn):
    nums = [int(r[0][1:]) for r in conn.execute("SELECT resource_id FROM resources")
            if r[0][1:].isdigit()]
    return f"R{(max(nums) + 1 if nums else 1):02d}"


def add_resource(conn, resource_id, name, rtype, capacity, facilities=()):
    conn.execute("INSERT INTO resources(resource_id,name,type,capacity,facilities) "
                 "VALUES (?,?,?,?,?)",
                 (resource_id, name, rtype, int(capacity),
                  ",".join(sorted(f.strip().lower() for f in facilities if f.strip()))))
    return resource_id


def get_resources(conn):
    out = {}
    for r in conn.execute("SELECT * FROM resources WHERE status = 'Active'"):
        d = dict(r)
        d["facilities"] = {f for f in d["facilities"].split(",") if f}
        out[d["resource_id"]] = d
    return out


# ---------------- events / bookings ----------------
def create_event(conn, organizer_id, title, etype, attendance, priority=1):
    cur = conn.execute("INSERT INTO events(organizer_id,title,type,expected_attendance,priority) "
                       "VALUES (?,?,?,?,?)", (organizer_id, title, etype, attendance, priority))
    return cur.lastrowid


def get_bookings(conn, date=None, resource_id=None):
    """Bookings in the shape E3 expects (keys: start, end, attendees, ...)."""
    sql = ("SELECT b.booking_id, e.title AS event, b.date, b.start_time AS start, "
           "b.end_time AS end, b.resource_id, e.expected_attendance AS attendees, b.status "
           "FROM bookings b JOIN events e ON e.event_id = b.event_id WHERE 1=1")
    params = []
    if date:
        sql += " AND b.date = ?"; params.append(date)
    if resource_id:
        sql += " AND b.resource_id = ?"; params.append(resource_id)
    sql += " ORDER BY b.date, b.start_time"
    return [dict(r) for r in conn.execute(sql, params)]


def is_available(conn, resource_id, date, start, end):
    """True when no confirmed booking overlaps [start, end) (HH:MM strings)."""
    n = conn.execute("SELECT COUNT(*) FROM bookings WHERE resource_id = ? AND date = ? "
                     "AND status = 'Confirmed' AND start_time < ? AND ? < end_time",
                     (resource_id, date, end, start)).fetchone()[0]
    return n == 0


def free_resources(conn, date, start, end, attendees=0, needs=()):
    """Active resources that fit the capacity and facilities and are free."""
    needs = {n.lower() for n in needs}
    found = [r for r in get_resources(conn).values()
             if r["capacity"] >= attendees and needs <= r["facilities"]
             and is_available(conn, r["resource_id"], date, start, end)]
    return sorted(found, key=lambda r: (r["capacity"], r["resource_id"]))


def check_resource_suitability(resource, attendees, needs=()):
    """Is this one resource suitable? Returns {"suitable": bool, "reason": str}.

    resource: one entry from get_resources(); capacity must be >= attendees and
    every needed facility must be present.
    """
    if resource.get("status", "Active") != "Active":
        return {"suitable": False, "reason": "Resource is not active"}
    if resource["capacity"] < attendees:
        return {"suitable": False,
                "reason": f"Capacity {resource['capacity']} < {attendees} attendees"}
    missing = sorted({n.lower() for n in needs} - set(resource["facilities"]))
    if missing:
        return {"suitable": False, "reason": "Missing: " + ", ".join(missing)}
    return {"suitable": True, "reason": "Capacity and facilities fit"}


def commit_booking(conn, event_id, resource_id, date, start, end, equipment=None):
    """Save one booking as a single ACID transaction.

    Returns {"status": "COMMITTED", "booking_id": n} or
            {"status": "ROLLED BACK", "reason": "..."}  (nothing saved).
    """
    equipment = equipment or {}
    try:
        conn.execute("BEGIN IMMEDIATE")            # write lock: one committer at a time
        if not is_available(conn, resource_id, date, start, end):
            raise BookingError("Slot already taken")
        cur = conn.execute("INSERT INTO bookings(event_id,resource_id,date,start_time,end_time,status) "
                           "VALUES (?,?,?,?,?, 'Confirmed')",
                           (event_id, resource_id, date, start, end))
        booking_id = cur.lastrowid
        for eq_id, qty in equipment.items():
            row = conn.execute("SELECT total_qty FROM equipment WHERE equipment_id = ? "
                               "AND status = 'Active'", (eq_id,)).fetchone()
            if row is None:
                raise BookingError(f"Unknown equipment: {eq_id}")
            used = conn.execute(
                "SELECT COALESCE(SUM(be.quantity),0) FROM booking_equipment be "
                "JOIN bookings b ON b.booking_id = be.booking_id "
                "WHERE be.equipment_id = ? AND b.date = ? AND b.status = 'Confirmed' "
                "AND b.start_time < ? AND ? < b.end_time", (eq_id, date, end, start)).fetchone()[0]
            if used + qty > row["total_qty"]:
                raise BookingError(f"Not enough {eq_id}: {row['total_qty'] - used} left")
            conn.execute("INSERT INTO booking_equipment VALUES (?,?,?)", (booking_id, eq_id, qty))
        conn.execute("UPDATE events SET status = 'Confirmed' WHERE event_id = ?", (event_id,))
        conn.execute("COMMIT")
        return {"status": "COMMITTED", "booking_id": booking_id}
    except (sqlite3.Error, BookingError) as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        return {"status": "ROLLED BACK", "reason": str(exc)}


def set_event_status(conn, event_id, status):
    """Set an event's state, e.g. 'Conflict Detected' or 'Rejected'.
    A Confirmed or Cancelled event is never changed here."""
    conn.execute("UPDATE events SET status = ? WHERE event_id = ? "
                 "AND status NOT IN ('Confirmed', 'Cancelled')", (status, event_id))


def list_events(conn, organizer_id=None):
    """Every event with its status; booked ones also show room, date and time."""
    sql = ("SELECT e.event_id, e.title, e.expected_attendance AS attendees, e.status, "
           "u.name AS organizer, b.resource_id, b.date, b.start_time AS start, b.end_time AS end "
           "FROM events e LEFT JOIN users u ON u.user_id = e.organizer_id "
           "LEFT JOIN bookings b ON b.event_id = e.event_id WHERE 1=1")
    params = []
    if organizer_id is not None:
        sql += " AND e.organizer_id = ?"
        params.append(organizer_id)
    sql += " ORDER BY e.event_id"
    return [dict(r) for r in conn.execute(sql, params)]


def booking_organizer(conn, booking_id):
    row = conn.execute("SELECT e.organizer_id FROM bookings b JOIN events e "
                       "ON e.event_id = b.event_id WHERE b.booking_id = ?", (booking_id,)).fetchone()
    return row[0] if row else None


def cancel_booking(conn, booking_id):
    """Cancel: slot is freed at once (booking row removed), event marked Cancelled."""
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT event_id FROM bookings WHERE booking_id = ?", (booking_id,)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return {"status": "NOT FOUND"}
        conn.execute("DELETE FROM booking_equipment WHERE booking_id = ?", (booking_id,))
        conn.execute("DELETE FROM bookings WHERE booking_id = ?", (booking_id,))
        conn.execute("UPDATE events SET status = 'Cancelled' WHERE event_id = ?", (row["event_id"],))
        conn.execute("COMMIT")
        return {"status": "CANCELLED"}
    except sqlite3.Error as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        return {"status": "ROLLED BACK", "reason": str(exc)}


def backup(conn, dest_path):
    """Copy the whole database to dest_path (owned by E2 / Admin)."""
    dest = sqlite3.connect(dest_path)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    return dest_path


if __name__ == "__main__":
    c = connect(":memory:")
    init_db(c); seed_sample(c)
    ev = create_event(c, None, "AI Hackathon", "Hackathon", 55)
    print(commit_booking(c, ev, "R01", "12 Oct", "10:00", "13:00"))
    print("R01 free 10:00-13:00?", is_available(c, "R01", "12 Oct", "10:00", "13:00"))
    ev2 = create_event(c, None, "TCS Placement Drive", "Placement", 45)
    print(commit_booking(c, ev2, "R01", "12 Oct", "10:00", "13:00"))
