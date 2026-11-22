"""Sample dataset from the Review 1 deck (slides 19-20)."""

RESOURCES = {
    "R01": {"name": "Computer Lab 1", "type": "Lab", "capacity": 60,
            "facilities": {"computers", "projector"}},
    "R02": {"name": "Computer Lab 2", "type": "Lab", "capacity": 50,
            "facilities": {"computers", "projector"}},
    "R03": {"name": "Seminar Hall", "type": "Hall", "capacity": 120,
            "facilities": {"projector", "microphone"}},
    "R04": {"name": "Auditorium", "type": "Auditorium", "capacity": 250,
            "facilities": {"audio", "projector", "stage"}},
}

BOOKINGS = [
    {"booking_id": "B001", "event": "AI Hackathon", "date": "12 Oct",
     "start": "10:00", "end": "13:00", "resource_id": "R01",
     "attendees": 55, "status": "Confirmed"},
    {"booking_id": "B002", "event": "TCS Placement Drive", "date": "12 Oct",
     "start": "10:00", "end": "13:00", "resource_id": "R01",
     "attendees": 45, "status": "Conflict"},
    {"booking_id": "B003", "event": "Club Activity", "date": "12 Oct",
     "start": "14:00", "end": "16:00", "resource_id": "R02",
     "attendees": 35, "status": "Candidate"},
    {"booking_id": "B004", "event": "Project Exhibition", "date": "13 Oct",
     "start": "09:00", "end": "12:00", "resource_id": "R03",
     "attendees": 100, "status": "Candidate"},
]
