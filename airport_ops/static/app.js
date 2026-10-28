const statusLabels = { SCHEDULED: '计划中', DELAYED: '延误', BOARDING: '登机中', DEPARTED: '已起飞', ARRIVED: '已到达', CANCELLED: '已取消' };
const directionLabels = { ARRIVAL: '到达', DEPARTURE: '出发' };
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function showToast(message, error = false) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.className = `toast show${error ? ' error' : ''}`;
  window.setTimeout(() => { toast.className = 'toast'; }, 3200);
}

async function api(url, options = {}) {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}

function formatTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
}

async function loadDashboard() {
  const data = await api('/api/dashboard');
  $('#metric-flights').textContent = data.flights_today;
  $('#metric-delayed').textContent = data.delayed_today;
  $('#metric-active').textContent = data.active_today;
  $('#metric-gates').textContent = `${data.gates_occupied} / ${data.gates_total}`;
}

async function loadOptions() {
  const data = await api('/api/options');
  $('#airline-select').innerHTML = data.airlines.map((a) => `<option value="${a.id}">${esc(a.code)} · ${esc(a.name)}</option>`).join('');
  $('#aircraft-select').innerHTML = data.aircraft_types.map((a) => `<option value="${a.id}">${esc(a.code)} · ${esc(a.name)}</option>`).join('');
}

async function loadGates() {
  const gates = await api('/api/gates');
  $('#gate-grid').innerHTML = gates.map((g) => `<article class="gate-card ${g.occupied ? 'occupied' : ''}"><span class="gate-code">${esc(g.code)}</span><span class="gate-terminal">${esc(g.terminal)} · ${g.gate_type === 'CONTACT' ? '廊桥位' : '远机位'}</span><span class="gate-state">${g.active ? (g.occupied ? '● 当前占用' : '● 当前空闲') : '已停用'}</span></article>`).join('');
}

async function loadFlights() {
  const params = new URLSearchParams(new FormData($('#filter-form')));
  for (const [key, value] of [...params.entries()]) if (!value) params.delete(key);
  const flights = await api(`/api/flights?${params}`);
  $('#flight-count').textContent = `显示 ${flights.length} 条航班记录（最多 500 条）`;
  if (!flights.length) {
    $('#flight-rows').innerHTML = '<tr><td colspan="7" class="empty-state">没有符合条件的航班。可先录入航班计划。</td></tr>';
    return;
  }
  const gates = await api('/api/gates');
  $('#flight-rows').innerHTML = flights.map((f) => `<tr>
    <td><span class="flight-primary">${esc(f.flight_no)} <span class="flight-secondary">${esc(f.airline_code)} · ${esc(f.airline_name)}</span></span></td>
    <td><span class="direction-tag">${directionLabels[f.direction] || f.direction}</span><span class="flight-secondary">${esc(f.origin_destination)} · ${esc(f.aircraft_code)}</span></td>
    <td>${formatTime(f.scheduled_time)}</td>
    <td><select class="gate-select" data-gate-flight="${f.id}"><option value="">${f.gate_code ? esc(f.gate_code) : '未分配'}</option>${gates.filter((g) => g.active && g.code !== f.gate_code).map((g) => `<option value="${g.id}">${esc(g.code)} · ${esc(g.terminal)}</option>`).join('')}</select></td>
    <td>${f.delay_minutes ? `<span class="status-badge status-DELAYED">${f.delay_minutes} 分钟</span><span class="flight-secondary">${esc(f.delay_reason)}</span>` : '—'}</td>
    <td><select class="status-select" data-status-flight="${f.id}">${Object.entries(statusLabels).map(([key, label]) => `<option value="${key}" ${f.status === key ? 'selected' : ''}>${label}</option>`).join('')}</select></td>
    <td><div class="row-actions"><button class="action-button" data-assign-flight="${f.id}">分配登机口</button><button class="action-button" data-delay-flight="${f.id}">登记延误</button></div></td>
  </tr>`).join('');
}

async function refresh() {
  try { await Promise.all([loadDashboard(), loadFlights(), loadGates()]); }
  catch (error) { showToast(error.message, true); }
}

$('#flight-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  try {
    await api('/api/flights', { method: 'POST', body: JSON.stringify(data) });
    event.currentTarget.reset();
    showToast('航班已保存');
    await refresh();
  } catch (error) { showToast(error.message, true); }
});

$('#filter-form').addEventListener('submit', (event) => { event.preventDefault(); loadFlights().catch((e) => showToast(e.message, true)); });
$('#refresh-button').addEventListener('click', refresh);
$('#new-flight-button').addEventListener('click', () => { $('#flight-entry').scrollIntoView({ behavior: 'smooth' }); $('#flight-form [name="flight_no"]').focus(); });
$('#toggle-form').addEventListener('click', () => {
  const form = $('#flight-form');
  const hidden = form.hidden;
  form.hidden = !hidden;
  $('#toggle-form').textContent = hidden ? '收起 −' : '展开 +';
});

$('#flight-rows').addEventListener('change', async (event) => {
  const statusFlight = event.target.dataset.statusFlight;
  if (statusFlight) {
    try { await api(`/api/flights/${statusFlight}/status`, { method: 'PATCH', body: JSON.stringify({ status: event.target.value }) }); showToast('航班状态已更新'); await refresh(); }
    catch (error) { showToast(error.message, true); await refresh(); }
  }
});

$('#flight-rows').addEventListener('click', async (event) => {
  const assignId = event.target.dataset.assignFlight;
  const delayId = event.target.dataset.delayFlight;
  try {
    if (assignId) {
      const select = document.querySelector(`[data-gate-flight="${assignId}"]`);
      if (!select.value) return showToast('请先在下拉框中选择登机口', true);
      await api(`/api/flights/${assignId}/assignments`, { method: 'POST', body: JSON.stringify({ gate_id: select.value }) });
      showToast('登机口分配成功');
      await refresh();
    }
    if (delayId) {
      const minutes = window.prompt('请输入延误分钟数');
      if (minutes === null) return;
      const reason = window.prompt('请输入延误原因');
      if (reason === null) return;
      await api(`/api/flights/${delayId}/delays`, { method: 'POST', body: JSON.stringify({ delay_minutes: minutes, reason }) });
      showToast('延误记录已保存');
      await refresh();
    }
  } catch (error) { showToast(error.message, true); }
});

$('#today-label').textContent = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });
loadOptions().then(refresh).catch((error) => showToast(error.message, true));

