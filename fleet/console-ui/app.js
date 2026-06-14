// Fleet Console UI — a lean SPA over the real Fleet Console API (#377, ADR 0009 §4).
// It ONLY calls the metadata-only endpoints in fleet_console/api.py. No business data
// is ever requested or rendered.

function apiBase() {
  return (document.getElementById('apiBase').value || '').replace(/\/$/, '');
}

async function api(path, opts) {
  const resp = await fetch(apiBase() + path, opts);
  const text = await resp.text();
  let body;
  try { body = text ? JSON.parse(text) : null; } catch (e) { body = text; }
  if (!resp.ok) {
    const detail = body && body.detail ? JSON.stringify(body.detail) : text;
    throw new Error(`${resp.status}: ${detail}`);
  }
  return body;
}

function setStatus(msg, isErr) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = isErr ? 'err' : '';
}

function badge(status) {
  return `<span class="badge s-${status}">${status}</span>`;
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;' }[c]));
}

function fmtDate(iso) {
  if (!iso) return '—';
  return esc(iso.slice(0, 10));
}

// ---- tabs ----
document.querySelectorAll('nav button').forEach(b => {
  b.onclick = () => {
    document.querySelectorAll('nav button').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    document.getElementById('tab-' + b.dataset.tab).classList.add('active');
  };
});

// ---- Roster ----
async function loadRoster() {
  try {
    const rows = await api('/fleet/roster');
    const body = document.querySelector('#rosterTable tbody');
    body.innerHTML = rows.map(r => `<tr>
      <td>${esc(r.customer_id)}</td>
      <td><code>${esc(r.license_id)}</code></td>
      <td>${esc(r.edition)}</td>
      <td>${badge(r.status)}</td>
      <td>${fmtDate(r.expires_at)}</td>
      <td>${r.last_seen ? fmtDate(r.last_seen) : '<span class="s-none">silent</span>'}</td>
      <td>${esc((r.entitled_modules || []).join(', '))}</td>
    </tr>`).join('') || '<tr><td colspan="7">No current licenses.</td></tr>';
    setStatus(`roster: ${rows.length} current`);
  } catch (e) { setStatus(e.message, true); }
}

// ---- Expiry ----
async function loadExpiring() {
  try {
    const within = document.getElementById('expWithin').value || 30;
    const rows = await api('/fleet/expiring?within_days=' + within);
    const body = document.querySelector('#expiryTable tbody');
    body.innerHTML = rows.map(r => `<tr>
      <td>${esc(r.customer_id)}</td><td><code>${esc(r.license_id)}</code></td>
      <td>${esc(r.edition)}</td><td>${badge(r.status)}</td><td>${fmtDate(r.expires_at)}</td>
    </tr>`).join('') || '<tr><td colspan="5">Nothing expiring in window.</td></tr>';
    setStatus(`expiring: ${rows.length}`);
  } catch (e) { setStatus(e.message, true); }
}

// ---- Entitlement ----
async function loadCustomer() {
  try {
    const cid = document.getElementById('entCustomer').value.trim();
    if (!cid) return;
    const v = await api('/fleet/customers/' + encodeURIComponent(cid));
    document.getElementById('entitlementOut').innerHTML = `
      <p><strong>${esc(v.customer_id)}</strong> — entitled modules:
        ${(v.entitled_modules || []).map(m => `<code>${esc(m)}</code>`).join(' ') || '<em>none</em>'}</p>
      <table><thead><tr><th>License</th><th>Edition</th><th>Status</th><th>Expires</th><th>Modules</th></tr></thead>
      <tbody>${v.licenses.map(r => `<tr>
        <td><code>${esc(r.license_id)}</code></td><td>${esc(r.edition)}</td>
        <td>${badge(r.status)}</td><td>${fmtDate(r.expires_at)}</td>
        <td>${esc((r.entitled_modules||[]).join(', '))}</td></tr>`).join('')}</tbody></table>`;
    setStatus(`customer ${cid}: ${v.licenses.length} license(s)`);
  } catch (e) {
    document.getElementById('entitlementOut').innerHTML = '';
    setStatus(e.message, true);
  }
}

// ---- Showback ----
async function loadShowback() {
  try {
    const stale = document.getElementById('sbStale').value;
    const q = stale ? '?silent_after_days=' + stale : '';
    const rows = await api('/fleet/showback' + q);
    const body = document.querySelector('#showbackTable tbody');
    body.innerHTML = rows.map(r => {
      const state = r.telemetry_state === 'none'
        ? `<span class="s-none">${esc(r.note || 'no telemetry')}</span>`
        : `<span class="badge s-current">${esc(r.telemetry_state)}</span>`;
      return `<tr>
        <td>${esc(r.customer_id)}</td><td><code>${esc(r.license_id)}</code></td>
        <td>${state}</td><td>${r.last_seen ? fmtDate(r.last_seen) : '—'}</td>
        <td>${esc((r.active_modules||[]).join(', '))}</td>
        <td>${esc(JSON.stringify(r.module_usage||{}))}</td>
        <td>${esc(JSON.stringify(r.showback_totals||{}))}</td>
        <td>${r.over_license ? '<span class="badge s-expired">over</span>' : 'ok'}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="8">No deployments.</td></tr>';
    setStatus(`showback: ${rows.length} rows`);
  } catch (e) { setStatus(e.message, true); }
}

// ---- Actions ----
function show(out) { document.getElementById('actionOut').textContent =
  typeof out === 'string' ? out : JSON.stringify(out, null, 2); }

function csv(id) {
  const v = document.getElementById(id).value.trim();
  return v ? v.split(',').map(s => s.trim()).filter(Boolean) : [];
}
function val(id) { const v = document.getElementById(id).value.trim(); return v || undefined; }

async function doIssue() {
  try {
    const body = {
      customer_id: val('iCustomer'), edition: val('iEdition'),
      license_id: val('iLicense'), quota_tier: val('iQuota'),
      entitled_modules: csv('iModules'),
      expires_at: val('iExpires'), delivery: val('iDelivery'),
      signing_key_pem: val('iKey'),
    };
    Object.keys(body).forEach(k => body[k] === undefined && delete body[k]);
    show(await api('/fleet/issue', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }));
    loadRoster();
  } catch (e) { show('ERROR ' + e.message); }
}

async function doRenew() {
  try {
    const body = {
      prior_license_id: val('rPrior'), license_id: val('rLicense'),
      customer_id: val('rCustomer') || '', edition: val('rEdition') || '',
      expires_at: val('rExpires'), signing_key_pem: val('rKey'),
    };
    Object.keys(body).forEach(k => body[k] === undefined && delete body[k]);
    show(await api('/fleet/renew', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }));
    loadRoster();
  } catch (e) { show('ERROR ' + e.message); }
}

async function doRevoke() {
  try {
    const body = { license_id: val('vLicense'), reason: val('vReason') };
    Object.keys(body).forEach(k => body[k] === undefined && delete body[k]);
    show(await api('/fleet/revoke', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }));
    loadRoster();
  } catch (e) { show('ERROR ' + e.message); }
}

loadRoster();
