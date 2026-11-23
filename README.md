# CampusFlow frontend

Responsive scheduling dashboard for the CS Department. The inspected workspace contained no scheduling backend, database, API definitions, or E1–E5 engines. This frontend therefore reads and writes only through HTTP endpoints and displays an unavailable/empty state when the service is absent; it does not fabricate event or room data.

## Run

Requires Node.js 18+ and npm. From this folder:

```sh
npm install
npm run dev
```

Copy `.env.example` to `.env` and set `VITE_API_BASE_URL` to the backend origin. If the API runs on the same Vite origin, configure a Vite proxy for `/api` in `vite.config.js`.

## API adapter

The adapter in `src/api.js` expects:

- `GET /api/dashboard`
- `GET /api/events`
- `GET /api/rooms`
- `GET /api/timetable?date=YYYY-MM-DD`
- `GET /api/booking-requests`
- `POST /api/events` with title, organizer, attendees, date, startTime, endTime, roomType and facilities
- `DELETE /api/events/:id` (adapter ready for cancellation controls)

The create action submits to the server and surfaces its response; capacity, facility validation, conflict detection, alternatives, and booking decisions must come from the existing server engines. Map endpoint names and payload fields in `src/api.js` to the actual E1–E5 contract before connecting a backend. No confirmation of successful booking is shown unless a successful API response is received.
