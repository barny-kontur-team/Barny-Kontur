// Тонкий слой над API. Все запросы идут на /api: в Docker их проксирует nginx,
// при локальной разработке — Vite (см. vite.config.js).
const BASE = '/api';

async function request(path, options = {}) {
  const response = await fetch(BASE + path, options);
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!response.ok) {
    const detail = body && body.detail;
    const message = typeof detail === 'string' ? detail :
      Array.isArray(detail) ? detail.map((entry) => entry.msg).join('; ') : 'Запрос не выполнен';
    throw Object.assign(new Error(message), { status: response.status });
  }
  return body;
}

function send(method, path, payload) {
  return request(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export const api = {
  users: () => request('/users'),
  clients: () => request('/clients'),
  work: () => request('/work'),
  calls: (clientId) => request(`/clients/${clientId}/calls`),
  take: (clientId, operatorId, takeover = false) =>
    send('POST', `/clients/${clientId}/take`, { operator_id: operatorId, takeover }),
  addCall: (clientId, payload) => send('POST', `/clients/${clientId}/calls`, payload),
  importClients: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/imports/clients', { method: 'POST', body: form });
  },
  importSnapshot: (file, date, period) => {
    const form = new FormData();
    form.append('file', file);
    form.append('snapshot_date', date);
    form.append('reporting_period', period);
    return request('/imports/snapshots', { method: 'POST', body: form });
  },
};
