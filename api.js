// Set VITE_API_BASE_URL in .env to point at the existing backend.
const API_BASE = (import.meta.env?.VITE_API_BASE_URL || '').replace(/\/$/, '');

export async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  });
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.message || body?.error || `Request failed (${response.status})`);
  return body;
}

// Expected REST endpoints. Adjust these paths to match the existing E1–E5 API.
export const api = {
  dashboard: () => apiRequest('/api/dashboard'),
  events: () => apiRequest('/api/events'),
  rooms: () => apiRequest('/api/rooms'),
  timetable: (date) => apiRequest(`/api/timetable?date=${encodeURIComponent(date)}`),
  requests: () => apiRequest('/api/booking-requests'),
  createEvent: (event) => apiRequest('/api/events', { method: 'POST', body: JSON.stringify(event) }),
  cancelEvent: (id) => apiRequest(`/api/events/${encodeURIComponent(id)}`, { method: 'DELETE' }),
};

export const apiConfigured = Boolean(API_BASE) || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
