/* Autoware health dashboard - read-only view over the AD API diagnostic graph. */

const OK = 0, WARN = 1, ERROR = 2, STALE = 3;
const LEVEL = { 0: 'OK', 1: 'WARN', 2: 'ERROR', 3: 'STALE' };

const S = {
  struct: null, nodeById: {}, leafById: {}, parentsOf: {},
  stream: null, view: 'overview', module: null,
  expanded: new Set(), selected: null, detail: null, devices: null,
};

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function ago(t) {
  if (t == null) return '—';
  const d = Date.now() / 1000 - t;
  if (d < 1) return 'now';
  if (d < 60) return d.toFixed(0) + 's';
  if (d < 3600) return Math.floor(d / 60) + 'm ' + Math.floor(d % 60) + 's';
  return Math.floor(d / 3600) + 'h';
}

/* ------------------------------------------------------------------ level */

function levelOf(id) {
  const st = S.stream;
  if (!st) return STALE;
  if (id.startsWith('s:')) return st.syn_levels[id] ?? STALE;
  if (st.graph_stale) return STALE;
  const i = parseInt(id.slice(1), 10);
  const arr = id[0] === 'n' ? st.node_levels : st.leaf_levels;
  return arr[i] ?? STALE;
}

const isLeaf = (id) => id.startsWith('d') || id.includes('#');

/* ----------------------------------------------------------------- struct */

async function loadStruct() {
  const r = await fetch('/api/struct');
  const st = await r.json();
  S.struct = st;
  S.nodeById = {}; S.leafById = {}; S.parentsOf = {};
  for (const n of st.nodes) S.nodeById[n.id] = n;
  for (const l of st.leaves) S.leafById[l.id] = l;
  for (const n of st.nodes) {
    for (const c of n.children) (S.parentsOf[c] ||= []).push(n.id);
    for (const l of n.leaves) (S.parentsOf[l] ||= []).push(n.id);
  }
  render();
}

function itemOf(id) { return S.nodeById[id] || S.leafById[id] || null; }

/* Expand every node that has a non-OK descendant, so a fault is visible the
   moment you open a module rather than after six clicks. */
function expandToProblems(rootId) {
  const seen = new Set();
  (function walk(id) {
    if (seen.has(id)) return levelOf(id) !== OK;
    seen.add(id);
    const n = S.nodeById[id];
    if (!n) return levelOf(id) !== OK;
    let bad = false;
    for (const c of n.children) bad = walk(c) || bad;
    for (const l of n.leaves) bad = (levelOf(l) !== OK) || bad;
    if (bad) S.expanded.add(id);
    return bad || levelOf(id) !== OK;
  })(rootId);
  S.expanded.add(rootId);
}

function revealPath(id) {
  let cur = id, guard = 0;
  while (cur && guard++ < 64) {
    const ps = S.parentsOf[cur] || [];
    if (!ps.length) break;
    S.expanded.add(ps[0]);
    cur = ps[0];
  }
}

/* ----------------------------------------------------------------- header */

function renderHeader() {
  const st = S.stream;
  const dot = document.getElementById('conn-dot');
  const txt = document.getElementById('conn-text');
  if (!st) { dot.className = 'dot'; txt.textContent = 'connecting…'; return; }
  const live = st.graph_ok;
  dot.className = 'dot ' + (live ? 'live' : 'dead');
  txt.innerHTML = live
    ? `graph live <span class="k">· ${st.graph_age == null ? '—' : st.graph_age.toFixed(1) + 's'}</span>`
    : (st.version ? 'graph stale' : 'waiting for Autoware');

  const h = st.header || {};
  const pills = [];
  const add = (k, v, cls) => pills.push(
    `<div class="pill"><span class="k">${esc(k)}</span><b class="${cls || ''}">${esc(v)}</b></div>`);
  if (h.operation_mode) add('mode', h.operation_mode,
    h.operation_mode === 'autonomous' ? 'up' : '');
  if (h.autoware_control !== undefined) add('control', h.autoware_control ? 'autoware' : 'manual');
  if (h.mrm) add('MRM', h.mrm, h.mrm === 'normal' ? 'up' : 'down');
  if (h.routing) add('route', h.routing);
  if (h.localization_init) add('localization', h.localization_init);
  if (st.ros_nodes) add('ROS nodes', st.ros_nodes);
  document.getElementById('header-pills').innerHTML = pills.join('');
}

/* --------------------------------------------------------------- overview */

function renderOverview() {
  const st = S.stream;
  const mods = (st && st.modules) || [];
  if (!mods.length) {
    return `<div class="card"><div class="empty">Waiting for the diagnostic graph…<br><br>
      Start Autoware, then this fills in automatically.</div></div>`;
  }
  const tiles = mods.map((m) => {
    const lvl = m.level ?? STALE;
    const badges = [];
    if (m.error) badges.push(`<span class="badge err">${m.error} error${m.error > 1 ? 's' : ''}</span>`);
    if (m.warn) badges.push(`<span class="badge warn">${m.warn} warning${m.warn > 1 ? 's' : ''}</span>`);
    if (!m.error && !m.warn && m.stale) badges.push(`<span class="badge">${m.stale} stale</span>`);
    if (!badges.length) badges.push('<span class="badge">all clear</span>');
    const beat = m.synthetic
      ? '<span class="dot live"></span> probed locally'
      : (st.graph_ok
        ? `<span class="dot live"></span> updated ${m.age == null ? '—' : m.age.toFixed(1) + 's ago'}`
        : '<span class="dot dead"></span> not reporting');
    return `<button class="tile l${lvl}" data-module="${esc(m.key)}">
      <div class="tile-top">
        <span class="tile-name">${esc(m.label)}</span>
        <span class="tile-state">${LEVEL[lvl]}</span>
      </div>
      <div class="tile-meta">${badges.join('')}${m.synthetic ? '<span class="badge syn">synthesised</span>' : ''}</div>
      <div class="heartbeat">${beat}</div>
    </button>`;
  }).join('');
  return `<div class="tiles">${tiles}</div>`;
}

/* ----------------------------------------------------------------- module */

function rowHtml(id, depth, parentLevel) {
  const item = itemOf(id);
  if (!item) return '';
  const lvl = levelOf(id);
  const leaf = isLeaf(id);
  const node = S.nodeById[id];
  const kids = node ? node.children.length + node.leaves.length : 0;
  const open = S.expanded.has(id);
  // A child that matches its unhealthy parent's level is why the parent is red.
  const culprit = parentLevel > OK && lvl === parentLevel;
  const cls = ['row', leaf ? 'leafrow' : 'noderow'];
  if (culprit) cls.push('culprit', parentLevel === WARN ? 'w' : '');
  if (S.selected === id) cls.push('sel');

  const msg = leaf ? (problemMessage(id) || '') : '';
  const twisty = kids ? (open ? '▾' : '▸') : '';

  let html = `<div class="${cls.join(' ')}" data-id="${esc(id)}"
      style="padding-left:${12 + depth * 17}px">
    <span class="tw">${twisty}</span>
    <span class="chip l${lvl}"></span>
    <span class="nm">${esc(leaf ? item.name : item.label)}</span>
    ${msg ? `<span class="msg">${esc(msg)}</span>` : '<span class="msg"></span>'}
    <span class="lvl l${lvl}" style="color:var(--${['ok','warn','err','stale'][lvl]})">${LEVEL[lvl]}</span>
  </div>`;

  if (node && open) {
    for (const c of node.children) html += rowHtml(c, depth + 1, lvl);
    for (const l of node.leaves) html += rowHtml(l, depth + 1, lvl);
  }
  return html;
}

function problemMessage(id) {
  const st = S.stream;
  if (!st) return '';
  const p = (st.problems || []).find((x) => x.id === id);
  return p ? p.message : '';
}

function renderModule() {
  const st = S.stream;
  const mod = (st.modules || []).find((m) => m.key === S.module);
  if (!mod) return renderOverview();
  const lvl = mod.level ?? STALE;
  return `<div class="card">
    <div class="crumb">
      <button data-back="1">← All modules</button>
      <span>/</span>
      <b>${esc(mod.label)}</b>
      <span class="badge ${lvl === ERROR ? 'err' : lvl === WARN ? 'warn' : ''}">${LEVEL[lvl]}</span>
      <span class="spacer" style="flex:1"></span>
      <span class="tname mono">${esc(mod.path)}</span>
    </div>
    <div class="tree">${rowHtml(mod.node_id, 0, OK)}</div>
    ${S.selected ? renderDetail() : ''}
  </div>`;
}

function renderDetail() {
  const item = itemOf(S.selected);
  if (!item) return '';
  const lvl = levelOf(S.selected);
  const d = (S.detail && S.detail.id === S.selected) ? S.detail.detail : null;
  const hist = (S.detail && S.detail.id === S.selected) ? (S.detail.history || []) : [];
  const rows = ((d && d.values) || [])
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td class="mono">${esc(v)}</td></tr>`).join('');
  const spark = hist.length > 1
    ? `<div class="spark">${hist.slice(-60).map(([, l]) =>
        `<i class="l${l}" style="height:${[35, 60, 100, 22][l]}%"></i>`).join('')}</div>
       <div class="tname">level history · ${hist.length} transitions, oldest ${ago(hist[0][0])} ago</div>`
    : '<div class="tname">no level changes recorded yet</div>';
  return `<div class="detail">
    <h3>${esc(item.name || item.label)}</h3>
    <div class="path mono">${esc(item.path)}</div>
    <div class="msgbox l${lvl}"><b style="color:var(--${['ok','warn','err','stale'][lvl]})">${LEVEL[lvl]}</b>
      &nbsp;${esc((d && d.message) || 'no message')}</div>
    ${d && d.hardware_id ? `<div class="tname mono" style="margin-bottom:8px">hardware_id: ${esc(d.hardware_id)}</div>` : ''}
    ${rows ? `<table class="kv">${rows}</table>` : '<div class="tname">no key/value data</div>'}
    ${spark}
  </div>`;
}

/* ---------------------------------------------------------------- devices */

function renderDevices() {
  const d = S.devices;
  if (!d) return '<div class="card"><div class="empty">Probing devices…</div></div>';
  const host = d.host || {};
  const groups = {};
  for (const dev of d.devices) (groups[dev.group] ||= []).push(dev);

  const reach = (dev) => dev.probe === 'none'
    ? '<span class="unk">not probed</span>'
    : dev.reachable === null || dev.reachable === undefined
      ? '<span class="unk">…</span>'
      : dev.reachable
        ? `<span class="up">● up</span> <span class="tname">${dev.rtt_ms ?? '—'} ms</span>`
        : '<span class="down">● unreachable</span>';

  const topicCell = (t) => {
    const exp = t.expect_hz || 0;
    const frac = exp ? Math.min(1, t.hz / exp) : (t.hz > 0 ? 1 : 0);
    const lvl = !t.seen ? 3 : t.warming ? 3
      : exp ? (t.hz < exp * 0.4 ? 2 : t.hz < exp * 0.7 ? 1 : 0) : (t.hz > 0 ? 0 : 2);
    return `<div class="hz">
      <div class="bar"><i class="l${lvl}" style="width:${(frac * 100).toFixed(0)}%"></i></div>
      <span class="mono">${t.hz.toFixed(1)} Hz</span>
      ${exp ? `<span class="tname">/ ${exp} Hz</span>` : ''}
    </div><div class="tname mono">${esc(t.topic)}${
      !t.seen ? ' · no publisher' : t.warming ? ' · measuring…' : ''}</div>`;
  };

  const body = Object.entries(groups).map(([g, devs]) => `
    <tr><td colspan="3" style="background:var(--panel-2);font-size:11px;
        letter-spacing:.6px;text-transform:uppercase;color:var(--dim)">${esc(g)}</td></tr>
    ${devs.map((dev) => `<tr>
      <td><b>${esc(dev.name)}</b>${dev.profile ? `<div class="tname">${esc(dev.profile)}</div>` : ''}</td>
      <td class="mono">${dev.ip ? esc(dev.ip) : '<span class="unk">—</span>'}
        <div class="tname">${reach(dev)}${dev.probe_age != null ? ` · ${dev.probe_age}s ago` : ''}</div></td>
      <td>${dev.topics.map(topicCell).join('<div style="height:7px"></div>') || '<span class="unk">—</span>'}</td>
    </tr>`).join('')}`).join('');

  return `<div class="card">
    <h2>Devices <span class="badge">rate over ${d.window_s}s window</span></h2>
    <table class="dev">
      <thead><tr><th>Device</th><th>Address</th><th>Topics</th></tr></thead>
      <tbody>
        <tr><td><b>${esc(host.name || 'Host')}</b><div class="tname">${esc(host.note || '')}</div></td>
          <td class="mono">${esc(host.ip || '—')}
            <div class="tname">${host.reachable ? '<span class="up">● up</span>' : '<span class="unk">—</span>'}</div></td>
          <td class="unk">—</td></tr>
        ${body}
      </tbody>
    </table>
  </div>`;
}

/* ----------------------------------------------------------------- events */

function renderEvents() {
  const ev = (S.stream && S.stream.events) || [];
  if (!ev.length) return '<div class="card"><div class="empty">No state changes recorded yet.</div></div>';
  return `<div class="card"><h2>Recent state changes</h2>
    ${ev.map((e) => `<div class="evt">
      <span class="t mono">${new Date(e.t * 1000).toLocaleTimeString()}</span>
      <span class="chip l${e.to}" style="display:inline-block;vertical-align:middle"></span>
      <b>${esc(e.name)}</b>
      <span class="tname">${LEVEL[e.from]} → ${LEVEL[e.to]}</span>
      ${e.message ? `<div class="tname" style="margin-left:78px">${esc(e.message)}</div>` : ''}
      <div class="tname mono" style="margin-left:78px">${esc(e.path)}</div>
    </div>`).join('')}</div>`;
}

/* ------------------------------------------------------------------- rail */

function renderRail() {
  const st = S.stream;
  const probs = (st && st.problems) || [];
  document.getElementById('prob-count').textContent = probs.length;
  const el = document.getElementById('rail');
  if (!probs.length) {
    el.innerHTML = '<div class="empty">Nothing to report.<br>All monitored items are OK.</div>';
    return;
  }
  el.innerHTML = probs.map((p) => {
    const cls = ['prob'];
    if (p.level === WARN) cls.push('w');
    if (p.level === STALE) cls.push('s');
    if (p.cleared_at) cls.push('cleared');
    return `<button class="${cls.join(' ')}" data-jump="${esc(p.id)}" data-mod="${esc(p.module || '')}">
      <div class="h"><span class="n">${esc(p.name)}</span>
        <span class="lvl" style="color:var(--${['ok','warn','err','stale'][p.level]})">${LEVEL[p.level]}</span></div>
      <div class="m">${esc(p.message || '')}</div>
      <div class="src">${esc(p.parent ? p.parent + ' · ' + (p.module || '?') : (p.module || '?'))} · ${
        p.cleared_at ? 'cleared ' + ago(p.cleared_at) + ' ago' : 'for ' + ago(p.since)}</div>
    </button>`;
  }).join('');
}

/* ----------------------------------------------------------------- render */

// ---------------------------------------------------------------- Vehicle tab
// Reads /api/vehicle, which reads ROS. Nothing here touches the chassis: the Segway
// SDK does not arbitrate serial access, and a second opener degrades the link for
// segway_vehicle_interface while reading 0xffff itself.
function renderVehicle() {
  const v = S.vehicle;
  if (!v) return '<div class="card"><h2>Vehicle</h2><p class="muted">loading…</p></div>';
  if (!v.running) {
    return '<div class="card"><h2>Vehicle</h2>' +
      '<p class="muted">The vehicle interface is not publishing.' +
      (v.reason ? ' (' + esc(v.reason) + ')' : '') + '</p>' +
      '<p class="muted">Start it with:<br><code>ros2 launch segway_vehicle_interface ' +
      'segway_vehicle_interface.launch.xml</code></p></div>';
  }
  const present = v.chassis_present;
  const rows = [
    ['Chassis', present ? 'replying' : 'NOT replying (values read 0xffff)'],
    ['Control mode', v.control_mode || '—'],
    ['Speed', (v.speed_mps ?? 0).toFixed(3) + ' m/s'],
    ['Yaw rate', (v.yaw_rate ?? 0).toFixed(3) + ' rad/s'],
    ['Battery', (v.battery_percent ?? 0) + ' %  (' + (v.battery_volts ?? 0) + ' V)'],
    ['Data age', (v.age_s ?? 0) + ' s'],
  ];
  return '<div class="card"><h2>Vehicle <span class="badge">Segway RMP Plus 401</span></h2>' +
    '<table class="kv">' + rows.map(function (r) {
      return '<tr><th>' + esc(r[0]) + '</th><td>' + esc(String(r[1])) + '</td></tr>';
    }).join('') + '</table>' +
    (present ? '' : '<p class="muted">The serial link is open but the chassis is not ' +
      'answering. Check that the vehicle is powered on.</p>') +
    '</div>';
}

// --------------------------------------------------------------- Foxglove tab
function renderFoxglove() {
  const f = S.foxglove;
  if (!f) return '<div class="card"><h2>Foxglove</h2><p class="muted">loading…</p></div>';
  const host = location.hostname;
  const state = f.bridge_running
    ? '<span class="badge ok">running</span>'
    : '<span class="badge err">not running</span>';
  let out = '<div class="card"><h2>Foxglove bridge ' + state + '</h2>';
  if (f.bridge_running) {
    out += '<p>Connect the Foxglove app to <code>ws://' + esc(host) + ':' +
           f.bridge_port + '</code></p>';
  } else {
    out += '<p class="muted">Start it with:<br><code>ros2 launch foxglove_bridge ' +
           'foxglove_bridge_launch.xml port:=8765 ' +
           'topic_whitelist:="$(./foxglove/build_whitelist.py)"</code></p>';
  }
  if (f.error) out += '<p class="muted">config: ' + esc(f.error) + '</p>';
  out += '</div><div class="card"><h2>Exposed topic groups</h2>' +
    '<p class="muted">Editing this restarts the bridge, which is a write path, so it ' +
    'lives in the control backend rather than here. This tab is read-only.</p>';
  out += '<table class="kv">' + (f.groups || []).map(function (g) {
    const badge = g.always ? '<span class="badge">always</span>'
                           : (g.enabled ? '<span class="badge ok">on</span>'
                                        : '<span class="badge">off</span>');
    return '<tr><th>' + esc(g.label) + ' ' + badge + '</th><td class="muted">' +
           esc((g.topics || []).join(', ')) + '</td></tr>';
  }).join('') + '</table></div>';
  return out;
}

function render() {
  renderHeader();
  renderRail();
  const main = document.getElementById('main');
  if (S.view === 'devices') main.innerHTML = renderDevices();
  else if (S.view === 'vehicle') main.innerHTML = renderVehicle();
  else if (S.view === 'foxglove') main.innerHTML = renderFoxglove();
  else if (S.view === 'events') main.innerHTML = renderEvents();
  else if (S.view === 'module' && S.stream) main.innerHTML = renderModule();
  else main.innerHTML = renderOverview();
  document.querySelectorAll('nav button').forEach((b) =>
    b.classList.toggle('on', b.dataset.view === (S.view === 'module' ? 'overview' : S.view)));
}

async function loadDetail(id) {
  const r = await fetch('/api/detail?id=' + encodeURIComponent(id));
  S.detail = await r.json();
  if (S.view === 'module') render();
}

function openModule(key) {
  S.module = key; S.view = 'module'; S.selected = null; S.detail = null;
  const mod = (S.stream.modules || []).find((m) => m.key === key);
  if (mod) expandToProblems(mod.node_id);
  render();
}

/* ------------------------------------------------------------------ wiring */

document.addEventListener('click', (e) => {
  const nav = e.target.closest('nav button');
  if (nav) {
    S.view = nav.dataset.view;
    if (S.view === 'devices') pollDevices();
    if (S.view === 'vehicle') pollVehicle();
    if (S.view === 'foxglove') pollFoxglove();
    render();
    return;
  }

  const tile = e.target.closest('.tile');
  if (tile) { openModule(tile.dataset.module); return; }

  if (e.target.closest('[data-back]')) { S.view = 'overview'; S.selected = null; render(); return; }

  const jump = e.target.closest('[data-jump]');
  if (jump) {
    const id = jump.dataset.jump;
    if (jump.dataset.mod) { S.module = jump.dataset.mod; S.view = 'module'; }
    revealPath(id); S.selected = id; loadDetail(id); render();
    setTimeout(() => document.querySelector('.row.sel')
      ?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 60);
    return;
  }

  const row = e.target.closest('.row');
  if (row) {
    const id = row.dataset.id;
    if (isLeaf(id)) {
      S.selected = S.selected === id ? null : id;
      if (S.selected) loadDetail(id); else S.detail = null;
    } else {
      S.expanded.has(id) ? S.expanded.delete(id) : S.expanded.add(id);
    }
    render();
  }
});

// Vehicle status moves fast enough to want a second-level refresh; the Foxglove
// config barely changes, so it is polled lazily and only while its tab is open.
let vehTimer = null;
async function pollVehicle() {
  try {
    S.vehicle = await (await fetch('/api/vehicle')).json();
  } catch (e) {
    S.vehicle = { running: false, reason: 'dashboard unreachable' };
  }
  if (S.view === 'vehicle') render();
  clearTimeout(vehTimer);
  if (S.view === 'vehicle') vehTimer = setTimeout(pollVehicle, 1000);
}

let foxTimer = null;
async function pollFoxglove() {
  try {
    S.foxglove = await (await fetch('/api/foxglove')).json();
  } catch (e) {
    S.foxglove = { groups: [], bridge_running: false, error: 'dashboard unreachable' };
  }
  if (S.view === 'foxglove') render();
  clearTimeout(foxTimer);
  if (S.view === 'foxglove') foxTimer = setTimeout(pollFoxglove, 5000);
}

let devTimer = null;
async function pollDevices() {
  const r = await fetch('/api/devices');
  S.devices = await r.json();
  if (S.view === 'devices') render();
  clearTimeout(devTimer);
  if (S.view === 'devices') devTimer = setTimeout(pollDevices, 3000);
}

function connect() {
  const es = new EventSource('/api/stream');
  es.onmessage = (e) => {
    S.stream = JSON.parse(e.data);
    if (!S.struct || S.struct.version !== S.stream.version) { loadStruct(); return; }
    if (S.selected) loadDetail(S.selected); else render();
  };
  es.onerror = () => {
    const dot = document.getElementById('conn-dot');
    dot.className = 'dot dead';
    document.getElementById('conn-text').textContent = 'disconnected — retrying';
  };
}

loadStruct();
connect();
