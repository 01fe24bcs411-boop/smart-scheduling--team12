import { api, apiConfigured } from './api.js';

const $ = (selector, root = document) => root.querySelector(selector);
const content = $('#page-content');
const state = { view: 'dashboard', dashboard: null, events: [], rooms: [], timetable: null, requests: [], loading: false, error: '' };
const today = new Date();
const dateISO = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const niceDate = (date, opts = { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }) => new Intl.DateTimeFormat('en', opts).format(date);
const esc = (value = '') => String(value).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const arrayFrom = (data, key) => Array.isArray(data) ? data : (Array.isArray(data?.[key]) ? data[key] : []);

$('#today-label').textContent = niceDate(today, { weekday: 'short', month: 'short', day: 'numeric' });
$('#year').textContent = today.getFullYear();

async function loadAll() {
  state.loading = true; state.error = ''; render();
  const jobs = [api.dashboard(), api.events(), api.rooms(), api.timetable(dateISO(today)), api.requests()];
  const results = await Promise.allSettled(jobs);
  const [dashboard, events, rooms, timetable, requests] = results;
  state.dashboard = dashboard.status === 'fulfilled' ? dashboard.value : null;
  state.events = events.status === 'fulfilled' ? arrayFrom(events.value, 'events') : [];
  state.rooms = rooms.status === 'fulfilled' ? arrayFrom(rooms.value, 'rooms') : [];
  state.timetable = timetable.status === 'fulfilled' ? timetable.value : null;
  state.requests = requests.status === 'fulfilled' ? arrayFrom(requests.value, 'requests') : [];
  const failures = results.filter((result) => result.status === 'rejected');
  state.loading = false;
  state.error = failures.length === jobs.length ? failures[0]?.reason?.message || 'The scheduling API is not responding.' : '';
  $('#request-count').textContent = requests.status === 'fulfilled' ? String(state.requests.length) : '—';
  render();
}

function pageHeading(eyebrow, title, subtitle, action = '') {
  return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${subtitle}</p></div>${action}</div>`;
}
function notice() {
  if (!state.error) return '';
  return `<div class="api-notice"><span class="notice-icon">!</span><div><strong>Scheduling service unavailable</strong><p>${esc(state.error)} Check that the backend is running and set <code>VITE_API_BASE_URL</code> if it runs on another address. Live booking data and actions will appear when the API is connected.</p></div><button class="notice-retry" id="retry-button">Retry</button></div>`;
}
function emptyState(icon, title, text, button = '') {
  return `<div class="empty-state"><div class="empty-icon">${icon}</div><strong>${title}</strong><p>${text}</p>${button}</div>`;
}
function metric(icon, label, value, caption, tint) {
  return `<article class="metric-card"><div class="metric-top"><span class="metric-icon ${tint}">${icon}</span><span class="metric-period">CURRENT</span></div><div class="metric-value">${value}</div><div class="metric-label">${label}</div><div class="metric-caption">${caption}</div></article>`;
}
function eventTime(event) {
  const start = event.startTime || event.start_time || event.start || '';
  const end = event.endTime || event.end_time || event.end || '';
  return start && end ? `${esc(String(start).slice(0, 5))} – ${esc(String(end).slice(0, 5))}` : (start ? esc(String(start).slice(0, 5)) : 'Time not set');
}
function eventDate(event) {
  const date = event.date || event.eventDate || event.event_date || event.startDate || '';
  if (!date) return 'Date not set';
  const parsed = new Date(`${String(date).slice(0, 10)}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? esc(date) : niceDate(parsed, { month: 'short', day: 'numeric' });
}
function eventRow(event) {
  const room = event.roomName || event.room_name || event.room?.name || event.room || 'Room pending';
  const status = event.status || 'Scheduled';
  const people = event.attendees ?? event.expectedAttendance ?? event.expected_attendance;
  return `<div class="event-row"><div class="event-date"><strong>${esc(eventDate(event))}</strong><span>${eventTime(event)}</span></div><span class="event-color"></span><div class="event-main"><strong>${esc(event.title || event.name || 'Untitled event')}</strong><span>${esc(event.organizer || event.organizerName || 'Organizer pending')}</span></div><div class="event-room"><span>${esc(room)}</span><small>${people == null ? 'Attendance not set' : `${esc(people)} attendees`}</small></div><span class="status-pill ${esc(String(status).toLowerCase().replace(/[^a-z]+/g, '-'))}">${esc(status)}</span></div>`;
}
function dashboardView() {
  const d = state.dashboard || {};
  const eventCount = d.totalEvents ?? d.total_events ?? (state.events.length || '—');
  const roomCount = d.availableRooms ?? d.available_rooms ?? (state.rooms.length || '—');
  const requestCount = d.pendingRequests ?? d.pending_requests ?? (state.requests.length || '—');
  const conflicts = d.conflicts ?? d.conflictCount ?? d.conflict_count ?? '—';
  const events = state.events.slice(0, 4);
  return `${pageHeading(`MONDAY, ${esc(niceDate(today, { month: 'long', day: 'numeric' }).toUpperCase())}`, 'Good day, Department Office <span class="wave">✳</span>', 'Here’s what’s happening across the CS department.', '<button class="button button-primary" id="create-event"><span class="plus">＋</span> Create event</button>')}${notice()}<div class="metrics-grid">${metric('◷', 'Scheduled events', eventCount, 'From the scheduling service', 'purple')}${metric('⌂', 'Available spaces', roomCount, 'Rooms returned by the service', 'mint')}${metric('⇄', 'Booking requests', requestCount, 'Requests awaiting review', 'amber')}${metric('⌁', 'Scheduling conflicts', conflicts, 'Detected by the scheduling engine', 'rose')}</div><div class="dashboard-grid"><section class="panel upcoming-panel"><div class="panel-heading"><div><div class="eyebrow">YOUR SCHEDULE</div><h2>Upcoming events</h2></div><a href="#events" class="text-link">All events <span>→</span></a></div><div class="event-list">${state.loading ? '<div class="loading-line"></div>'.repeat(3) : events.length ? events.map(eventRow).join('') : emptyState('◷', 'No events to show yet', 'Events from your connected scheduling service will appear here.', '<button class="button button-secondary" id="create-event-empty">Create an event</button>')}</div></section><section class="panel availability-panel"><div class="panel-heading"><div><div class="eyebrow">CAMPUS SPACES</div><h2>Room availability</h2></div><a href="#rooms" class="text-link">Browse rooms <span>→</span></a></div>${state.loading ? '<div class="loading-line"></div>'.repeat(3) : state.rooms.length ? roomAvailability() : emptyState('⌂', 'No room data available', 'Connect the rooms API to see live capacities, facilities and availability.')}</section></div><div class="bottom-grid"><section class="panel week-panel"><div class="panel-heading"><div><div class="eyebrow">AT A GLANCE</div><h2>This week</h2></div><a href="#timetable" class="text-link">Open timetable <span>→</span></a></div>${weekStrip()}</section><section class="panel tip-panel"><div class="tip-symbol">✳</div><div><div class="eyebrow">SMART SCHEDULING</div><h3>Room for every good idea.</h3><p>Availability and conflict checks come from your department scheduling engine.</p><a href="#rooms" class="text-link">Explore spaces <span>→</span></a></div></section></div>`;
}
function roomAvailability() {
  const rooms = state.rooms.slice(0, 4);
  return `<div class="room-list">${rooms.map((room) => {
    const name = room.name || room.roomName || room.room_name || 'Unnamed room';
    const type = room.type || room.roomType || room.room_type || 'Space';
    const capacity = room.capacity ?? room.maxCapacity ?? room.max_capacity;
    const available = room.available ?? room.isAvailable ?? room.is_available;
    return `<div class="room-row"><span class="room-type-icon">${String(type).toLowerCase().includes('lab') ? '⌘' : String(type).toLowerCase().includes('hall') ? '▤' : '⌂'}</span><div class="room-info"><strong>${esc(name)}</strong><small>${esc(type)}${capacity == null ? '' : ` · ${esc(capacity)} seats`}</small></div><span class="availability ${available === true ? 'available' : available === false ? 'occupied' : 'unknown'}"><i></i>${available === true ? 'Available' : available === false ? 'Occupied' : 'Status unknown'}</span></div>`;
  }).join('')}</div>`;
}
function weekStrip() {
  const start = new Date(today); const day = (today.getDay() + 6) % 7; start.setDate(today.getDate() - day);
  return `<div class="week-strip">${Array.from({ length: 7 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); const active = dateISO(d) === dateISO(today); const count = state.events.filter((event) => String(event.date || event.eventDate || event.event_date || '').slice(0, 10) === dateISO(d)).length; return `<div class="week-day ${active ? 'current' : ''}"><span>${new Intl.DateTimeFormat('en', { weekday: 'short' }).format(d)}</span><strong>${d.getDate()}</strong><i>${count ? `${count} event${count > 1 ? 's' : ''}` : '—'}</i></div>`; }).join('')}</div>`;
}
function eventsView() {
  const events = state.events;
  return `${pageHeading('DEPARTMENT CALENDAR', 'Events', 'Manage bookings and keep everyone in the loop.', '<button class="button button-primary" id="create-event"><span class="plus">＋</span> Create event</button>')}${notice()}<section class="panel data-panel"><div class="table-toolbar"><div><strong>${events.length} event${events.length === 1 ? '' : 's'}</strong><span> · Live schedule</span></div><button class="button button-quiet" id="refresh-inline">⟳ Refresh</button></div>${state.loading ? '<div class="loading-line"></div>'.repeat(5) : events.length ? `<div class="event-list full-event-list">${events.map(eventRow).join('')}</div>` : emptyState('◷', 'No events found', 'When events are returned by the scheduling service, they’ll show up here.', '<button class="button button-primary" id="create-event-empty">Create an event</button>')}</section>`;
}
function roomsView() {
  return `${pageHeading('FIND A SPACE', 'Rooms & spaces', 'Compare capacity, facilities and availability for your event.', '')}${notice()}${state.loading ? '<div class="metrics-grid">'.concat('<div class="loading-card"></div>'.repeat(4), '</div>') : state.rooms.length ? `<div class="rooms-grid">${state.rooms.map((room) => { const name = room.name || room.roomName || room.room_name || 'Unnamed room'; const type = room.type || room.roomType || room.room_type || 'Space'; const capacity = room.capacity ?? room.maxCapacity ?? room.max_capacity; const features = room.facilities || room.features || []; const available = room.available ?? room.isAvailable ?? room.is_available; return `<article class="room-card"><div class="room-card-top"><span class="room-type-icon">${String(type).toLowerCase().includes('lab') ? '⌘' : String(type).toLowerCase().includes('hall') ? '▤' : '⌂'}</span><span class="availability ${available === true ? 'available' : available === false ? 'occupied' : 'unknown'}"><i></i>${available === true ? 'Available' : available === false ? 'Occupied' : 'Status unknown'}</span></div><div class="room-kind">${esc(type)}</div><h3>${esc(name)}</h3><p class="room-capacity">♙ &nbsp;Capacity ${capacity == null ? 'not provided' : esc(capacity)}</p><div class="facility-tags">${(Array.isArray(features) ? features : String(features).split(',')).filter(Boolean).map((f) => `<span>${esc(typeof f === 'string' ? f : f.name || f.label || '')}</span>`).join('') || '<span>Facility details unavailable</span>'}</div></article>`; }).join('')}</div>` : `<section class="panel">${emptyState('⌂', 'No spaces to display', 'Room inventory will appear here when the rooms API is connected.')}</section>`}`;
}
function timetableView() {
  const rows = arrayFrom(state.timetable, 'events');
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
  const slots = ['09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00'];
  return `${pageHeading('ADMIN VIEW', 'Department timetable', 'A clear view of scheduled activity across campus spaces.', '<label class="date-picker-label">Week of <input type="date" id="timetable-date" value="${dateISO(today)}" /></label>')}${notice()}<section class="panel timetable-panel"><div class="table-scroll"><div class="timetable"><div class="time-cell timetable-head">TIME</div>${days.map((d) => `<div class="timetable-head day-head">${d}</div>`).join('')}${slots.map((slot) => `<div class="time-cell">${slot}</div>${days.map((day) => { const found = rows.find((e) => { const time = String(e.startTime || e.start_time || e.start || '').slice(0, 5); const dayText = String(e.day || e.weekday || '').slice(0, 3).toLowerCase(); return time === slot && dayText === day.toLowerCase(); }); return `<div class="timetable-cell">${found ? `<div class="timetable-event"><strong>${esc(found.title || found.name || 'Event')}</strong><span>${esc(found.roomName || found.room_name || found.room || 'Room pending')}</span></div>` : ''}</div>`; }).join('')}`).join('')}</div></div>${rows.length ? '' : emptyState('▦', 'Timetable is waiting for live data', 'Connect the timetable API to see scheduled events and room assignments.')}</section>`;
}
function requestsView() {
  return `${pageHeading('REVIEW QUEUE', 'Booking requests', 'Review requests and let the scheduling service validate conflicts.', '')}${notice()}<section class="panel data-panel">${state.requests.length ? `<div class="request-list">${state.requests.map((request) => `<div class="request-row"><div class="request-avatar">${esc(String(request.organizer || request.requester || '?').slice(0, 2).toUpperCase())}</div><div class="request-details"><strong>${esc(request.title || request.eventName || 'Untitled request')}</strong><span>${esc(request.organizer || request.requester || 'Organizer not specified')} · ${eventDate(request)}</span></div><span class="status-pill pending">${esc(request.status || 'Pending')}</span></div>`).join('')}</div>` : emptyState('⇄', 'No booking requests', 'Requests from event organizers will appear here when supplied by the API.')}</section>`;
}
function peopleView() {
  return `${pageHeading('YOUR DEPARTMENT', 'People', 'Event organizers and administrators in your workspace.', '')}${notice()}<section class="panel">${emptyState('♙', 'People directory unavailable', 'Connect a people endpoint to display department members and roles.')}</section>`;
}
function render() {
  const labels = { dashboard: 'Dashboard', timetable: 'Timetable', events: 'Events', rooms: 'Rooms & spaces', requests: 'Booking requests', people: 'People' };
  $('#breadcrumb-current').textContent = labels[state.view] || 'Dashboard';
  document.querySelectorAll('.nav-link').forEach((link) => link.classList.toggle('active', link.dataset.view === state.view));
  const views = { dashboard: dashboardView, events: eventsView, rooms: roomsView, timetable: timetableView, requests: requestsView, people: peopleView };
  content.innerHTML = (views[state.view] || dashboardView)();
  $('#retry-button')?.addEventListener('click', loadAll);
  $('#create-event')?.addEventListener('click', openEventDialog);
  $('#create-event-empty')?.addEventListener('click', openEventDialog);
  $('#refresh-inline')?.addEventListener('click', loadAll);
  $('#timetable-date')?.addEventListener('change', async (e) => { try { state.timetable = await api.timetable(e.target.value); state.error = ''; } catch (err) { state.error = err.message; } render(); });
}

function openEventDialog() {
  $('#form-error').textContent = '';
  const form = $('#event-form'); form.reset();
  const date = $('input[name="date"]', form); date.min = dateISO(today); date.value = dateISO(today);
  $('#event-dialog').showModal();
}
document.querySelectorAll('.close-dialog').forEach((button) => button.addEventListener('click', () => $('#event-dialog').close()));
$('#event-dialog').addEventListener('click', (e) => { if (e.target === $('#event-dialog')) $('#event-dialog').close(); });
$('#event-form').addEventListener('submit', async (e) => {
  e.preventDefault(); const form = e.currentTarget; const data = new FormData(form); const error = $('#form-error'); error.textContent = '';
  if (data.get('endTime') <= data.get('startTime')) { error.textContent = 'End time must be later than start time.'; return; }
  const attendees = Number(data.get('attendees'));
  if (!Number.isInteger(attendees) || attendees < 1) { error.textContent = 'Enter an attendance number greater than zero.'; return; }
  const payload = { title: data.get('title').trim(), organizer: data.get('organizer').trim(), attendees, date: data.get('date'), startTime: data.get('startTime'), endTime: data.get('endTime'), roomType: data.get('roomType') || null, facilities: String(data.get('facilities') || '').split(',').map((s) => s.trim()).filter(Boolean) };
  const submit = $('button[type="submit"]', form); submit.disabled = true; submit.innerHTML = '<span class="spinner"></span> Checking…';
  try {
    const result = await api.createEvent(payload);
    $('#event-dialog').close();
    if (result?.alternatives?.length || result?.suggestions?.length || result?.conflicts?.length) showToast(result.message || 'The scheduler returned alternatives or conflicts. Review the response in your event request.', 'warning');
    else showToast(result?.message || 'Request sent to the scheduling service.', 'success');
    await loadAll();
  } catch (err) { error.textContent = `${err.message}. No event was created.`; }
  finally { submit.disabled = false; submit.innerHTML = 'Check availability <span>→</span>'; }
});

function showToast(message, kind) { const node = document.createElement('div'); node.className = `toast ${kind}`; node.textContent = message; $('#toast-region').append(node); setTimeout(() => node.remove(), 4500); }
document.querySelectorAll('.nav-link').forEach((link) => link.addEventListener('click', (e) => { e.preventDefault(); state.view = link.dataset.view; history.replaceState(null, '', `#${state.view}`); render(); $('#sidebar').classList.remove('sidebar-open'); }));
$('#refresh-button').addEventListener('click', loadAll);
$('#mobile-menu').addEventListener('click', () => $('#sidebar').classList.toggle('sidebar-open'));
$('#help-button').addEventListener('click', () => showToast('Help center is not configured for this workspace.', 'warning'));
$('#profile-button').addEventListener('click', () => showToast('Role switching requires the department authentication service, which is not present in this workspace.', 'warning'));
$('#role-label').textContent = apiConfigured ? 'Administrator' : 'API not configured';
state.view = location.hash.slice(1) in { dashboard: 1, timetable: 1, events: 1, rooms: 1, requests: 1, people: 1 } ? location.hash.slice(1) : 'dashboard';
loadAll();
