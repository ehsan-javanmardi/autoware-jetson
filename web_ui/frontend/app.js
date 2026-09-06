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



// ============================================================== tab routing
// Four top-level tabs; Autoware carries sub-tabs. The old single-level `view`
// still drives the diagnostic renderers, so it is derived from the pair rather
// than replaced, which keeps renderOverview/renderModule/renderEvents intact.
const TABS = {
  hardware: { label: 'Hardware', subs: [['sensors', 'Sensors'], ['chassis', 'Vehicle chassis']] },
  foxglove: { label: 'Foxglove', subs: [] },
  autoware: { label: 'Autoware', subs: [['run', 'Run'], ['health', 'Health'], ['events', 'Events'], ['goals', 'Destinations']] },
  remote:   { label: 'Remote drive', subs: [] },
};
S.tab = S.tab || 'hardware';
S.sub = S.sub || 'sensors';

function renderSubtabs() {
  const el = document.getElementById('subtabs');
  const subs = (TABS[S.tab] || {}).subs || [];
  el.innerHTML = subs.map(function (s) {
    return '<button data-sub="' + s[0] + '"' + (S.sub === s[0] ? ' class="on"' : '') + '>' +
           esc(s[1]) + '</button>';
  }).join('');
}

function tile(label, value, sub, cls) {
  return '<div class="tile ' + (cls || '') + '"><div class="lab">' + esc(label) +
         '</div><div class="val">' + esc(value) + '</div>' +
         (sub ? '<div class="sub">' + esc(sub) + '</div>' : '') + '</div>';
}

function notice(text, cls) {
  return '<div class="notice ' + (cls || '') + '">' + text + '</div>';
}

// ------------------------------------------------------------ Hardware tab
function renderChassis() {
  const v = S.vehicle;
  if (!v) return '<div class="card"><p class="muted">loading…</p></div>';
  if (!v.running) {
    return notice('<b>The vehicle interface is not running.</b> Nothing is reading the ' +
      'Segway, so there is no chassis data to show.' +
      '<br><br>Start it from a terminal:<br>' +
      '<code>ros2 launch segway_vehicle_interface segway_vehicle_interface.launch.xml</code>' +
      '<br><br>Without <code>allow_control:=true</code> it publishes status and cannot ' +
      'move the base.', 'warn');
  }
  const present = v.chassis_present;
  const soc = v.battery_percent == null ? 0 : v.battery_percent;
  const batCls = soc < 20 ? 'err' : (soc < 40 ? 'warn' : 'ok');
  const mode = v.control_mode || '—';
  let out = '<div class="tiles">' +
    tile('Chassis link', present ? 'replying' : 'no reply', present ? '' : 'values read 0xffff',
         present ? 'ok' : 'err') +
    tile('Control mode', mode, mode === 'autonomous' ? 'motors enabled' : 'motors disabled',
         mode === 'autonomous' ? 'warn' : 'ok') +
    tile('Battery', soc + ' %', (v.battery_volts ?? 0) + ' V', batCls) +
    tile('Speed', (v.speed_mps ?? 0).toFixed(2) + ' m/s',
         'yaw ' + (v.yaw_rate ?? 0).toFixed(2) + ' rad/s', 'ok') +
    '</div>';
  if (!present) {
    out += notice('The serial port is open but the chassis is not answering. Check that ' +
      'the vehicle and its controller are powered on. If the USB cable was moved, the ' +
      'converter may have re-enumerated — the <code>/dev/segway</code> symlink handles ' +
      'that, but the chassis still has to be on.', 'err');
  }
  out += '<div class="card" style="margin-top:14px"><h2>Detail</h2><table class="kv">' +
    '<tr><th>Data age</th><td>' + esc(v.age_s ?? '—') + ' s</td></tr>' +
    '<tr><th>Reported speed</th><td>' + (v.speed_mps ?? 0).toFixed(3) + ' m/s</td></tr>' +
    '<tr><th>Reported yaw rate</th><td>' + (v.yaw_rate ?? 0).toFixed(3) + ' rad/s</td></tr>' +
    '</table></div>';
  return out;
}

// ------------------------------------------------------------ Foxglove tab
function renderFoxgloveTab() {
  const f = S.foxglove;
  if (!f) return '<div class="card"><p class="muted">loading…</p></div>';
  const host = location.hostname;
  const url = 'ws://' + host + ':' + (f.bridge_port || 8765);
  let out = '<div class="tiles">' +
    tile('Bridge', f.bridge_running ? 'running' : 'not running',
         'port ' + (f.bridge_port || 8765), f.bridge_running ? 'ok' : 'off') +
    tile('Topic groups', String((f.groups || []).filter(function (g) { return g.enabled; }).length) +
         ' of ' + (f.groups || []).length, 'exposed to clients', 'ok') +
    '</div>';
  if (f.bridge_running) {
    out += '<div class="card" style="margin-top:14px"><h2>Connect</h2>' +
      '<p>In the Foxglove app choose <b>Open connection → Foxglove WebSocket</b> and enter:</p>' +
      '<p><code style="font-size:15px">' + esc(url) + '</code></p>' +
      '<p class="muted">This is a WebSocket, not a web page — opening it in a browser ' +
      'will not work. Use the Foxglove iPad app or app.foxglove.dev.</p></div>';
  } else {
    out += notice('<b>The bridge is not running.</b> Start it from a terminal:<br>' +
      '<code>ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 ' +
      'topic_whitelist:="$(./foxglove/build_whitelist.py)"</code>', 'warn');
  }
  out += '<div class="card" style="margin-top:14px"><h2>Exposed topic groups</h2>' +
    '<table class="kv">' + (f.groups || []).map(function (g) {
      const b = g.always ? '<span class="badge">always</span>'
                         : (g.enabled ? '<span class="badge ok">on</span>'
                                      : '<span class="badge">off</span>');
      return '<tr><th>' + esc(g.label) + ' ' + b + '</th><td class="muted">' +
             esc((g.topics || []).join(', ')) + '</td></tr>';
    }).join('') + '</table>' +
    '<p class="muted">Changing the selection restarts the bridge, which is a write, so it ' +
    'lives in the control backend rather than here.</p></div>';
  return out;
}

// ------------------------------------------------------------ Autoware tab
// Every control here is a write, so it goes to the control backend on 8843
// rather than to this process, which has no ROS publishers at all.
function prereqs(what) {
  // Show every prerequisite at once with its state. The previous version reported
  // only the first missing one, so you fixed it, reloaded, and were told about the
  // next -- which is a poor way to learn you needed three things.
  const v = S.vehicle || {};
  const items = [
    ['Web UI', true,
     'ros2 launch segway_web_ui web_ui.launch.xml'],
    ['Control backend', !!(S.ctrl && S.ctrl.up),
     'ros2 launch segway_web_control web_control.launch.xml'],
    ['Vehicle interface', !!v.running,
     'ros2 launch segway_vehicle_interface segway_vehicle_interface.launch.xml allow_control:=true'],
  ];
  const missing = items.filter(function (i) { return !i[1]; });
  if (!missing.length) return '';

  let out = '<div class="card"><h2>' + esc(what) + ' needs three things running</h2>' +
    '<table class="kv">' + items.map(function (i) {
      const badge = i[1] ? '<span class="badge ok">running</span>'
                         : '<span class="badge err">not running</span>';
      return '<tr><th>' + esc(i[0]) + '</th><td>' + badge + '</td></tr>';
    }).join('') + '</table>';

  out += '<p class="muted" style="margin-top:12px">Start the missing one' +
    (missing.length > 1 ? 's' : '') + ' in a terminal:</p>';
  out += missing.map(function (i) {
    return '<p><code>' + esc(i[2]) + '</code></p>';
  }).join('');
  out += '<p class="muted">Each needs <code>source install/setup.bash</code> first. ' +
    'The dashboard cannot start them itself: it creates no ROS publishers and no service ' +
    'clients, which is what stops it commanding the vehicle.</p></div>';
  return out;
}

function renderAutowareRun() {
  const a = S.autoware || {};
  const up = a.autoware_running;
  let out = '<div class="tiles">' +
    tile('Autoware', up ? 'running' : 'not running',
         up ? (a.node_count || 0) + ' nodes' : 'nothing launched', up ? 'ok' : 'off') +
    tile('Control backend', S.ctrl && S.ctrl.up ? 'running' : 'not running',
         'port 8843', S.ctrl && S.ctrl.up ? 'ok' : 'off') +
    '</div>';
  if (!S.ctrl || !S.ctrl.up) return out + prereqs('Starting and stopping Autoware');
  out += '<div class="card" style="margin-top:14px"><h2>Run</h2>' +
    '<p class="muted">Launches <code>autoware_kashiwa.sh</code>: vehicle_model segway, ' +
    'sensor_model segway_sensor_kit, Livox profile.</p>' +
    '<div class="btnrow">' +
    '<button class="act go" data-act="autoware_start"' + (up ? ' disabled' : '') + '>Start Autoware</button>' +
    '<button class="act stop" data-act="autoware_stop"' + (up ? '' : ' disabled') + '>Stop Autoware</button>' +
    '</div></div>';
  return out;
}

function renderGoals() {
  if (!S.ctrl || !S.ctrl.up) return prereqs('Setting destinations');
  const g = (S.autoware && S.autoware.goals) || {};
  const pts = g.points || [];
  let out = '<div class="card"><h2>Operation</h2><div class="btnrow">' +
    '<button class="act go" data-act="engage">Engage</button>' +
    '<button class="act stop" data-act="disengage">Stop</button>' +
    '<button class="act" data-act="mode_auto">Autonomous</button>' +
    '<button class="act" data-act="mode_manual">Manual</button>' +
    '</div></div>';
  out += '<div class="card" style="margin-top:14px"><h2>Destinations <span class="badge">' +
    pts.length + '</span></h2>' +
    '<p class="muted">Add goals in order. Repeat mode returns from the last to the first ' +
    'and keeps going until stopped.</p>' +
    '<table class="kv">' + (pts.length ? pts.map(function (pt, i) {
      return '<tr><th>' + (i + 1) + '</th><td>' + esc(pt.label || (pt.x + ', ' + pt.y)) + '</td></tr>';
    }).join('') : '<tr><td class="muted">none set</td></tr>') + '</table>' +
    '<div class="btnrow">' +
    '<button class="act" data-act="goal_add">Add current pose</button>' +
    '<button class="act" data-act="goal_clear">Clear</button>' +
    '</div>' +
    '<div class="btnrow">' +
    '<button class="act" data-act="seq_step"' + (g.mode === 'step' ? ' disabled' : '') + '>Step-by-step</button>' +
    '<button class="act" data-act="seq_route"' + (g.mode === 'route' ? ' disabled' : '') + '>Single route</button>' +
    '<button class="act" data-act="repeat_toggle">' + (g.repeat ? 'Repeat: ON' : 'Repeat: off') + '</button>' +
    '</div>' +
    '<div class="btnrow">' +
    '<button class="act go" data-act="run_goals">Run</button>' +
    '<button class="act stop" data-act="stop_goals">Stop sequence</button>' +
    '</div></div>';
  return out;
}

// -------------------------------------------------------- Remote drive tab
// Analogue joystick rather than a D-pad, taken from tools/segway_dashboard which
// was tuned against this chassis. Steering is continuous on an Ackermann base:
// four buttons can only ask for full lock or nothing, which is why the first
// version turned so badly.
function renderRemote() {
  const v = S.vehicle || {};
  const r = (S.autoware && S.autoware.remote) || {};
  const armed = !!r.enabled;
  const inSitu = !!r.in_situ;
  const ready = S.ctrl && S.ctrl.up && v.chassis_present;
  const soc = v.battery_percent ?? 0;
  const batCls = soc < 20 ? 'err' : (soc < 40 ? 'warn' : 'ok');

  const gate = prereqs('Remote driving');
  if (gate) return gate;

  let out = '<div class="armed-banner' + (armed ? '' : ' off') + '">' +
    (armed ? '⚠ ARMED — the vehicle moves while the joystick is held'
           : '○ Disarmed — arm below to drive') + '</div>';

  out += '<div class="drive-wrap" style="margin-top:14px">';

  // --- joystick
  out += '<div class="card pad-wrap"><h2 style="align-self:flex-start">Drive</h2>' +
    '<div class="pad' + (armed ? '' : ' disabled') + '" id="pad">' +
    '<div class="ring"></div><div class="cross"></div><div class="cross-v"></div>' +
    '<div class="knob" id="knob"></div>' +
    '<div class="hint" id="padhint">' +
      (armed ? 'hold and drag to drive' : 'arm to enable') + '</div></div>' +
    '<div class="speed-row" style="width:100%;margin-top:30px">' +
    '<span class="muted">Max</span>' +
    '<input type="range" id="spd" min="0.1" max="1.5" step="0.1" value="' +
      (r.max_speed ?? 0.5) + '"' + (ready ? '' : ' disabled') + '>' +
    '<span class="v" id="spdv">' + (r.max_speed ?? 0.5) + ' m/s</span></div>' +
    '</div>';

  // --- status + arming + e-stop
  out += '<div class="card">' +
    '<h2>Battery</h2>' +
    '<div class="bar"><i class="' + batCls + '" style="width:' + Math.max(0, Math.min(100, soc)) + '%"></i></div>' +
    '<div class="readout">' +
      '<div><div class="k">Charge</div><div class="v">' + soc + ' %</div></div>' +
      '<div><div class="k">Voltage</div><div class="v">' + (v.battery_volts ?? 0) + ' V</div></div>' +
      '<div><div class="k">Speed</div><div class="v">' + (v.speed_mps ?? 0).toFixed(2) + ' m/s</div></div>' +
      '<div><div class="k">Yaw rate</div><div class="v">' + (v.yaw_rate ?? 0).toFixed(2) + '</div></div>' +
    '</div>' +
    '<h2 style="margin-top:18px">Steering</h2>' +
    '<div class="modeswitch">' +
      '<button data-act="mode_ackermann" class="' + (inSitu ? '' : 'on') + '">Ackermann</button>' +
      '<button data-act="mode_in_situ" class="' + (inSitu ? 'on' : '') + '">Spin in place</button>' +
    '</div>' +
    (inSitu ? notice('Spin-in-place uses a special chassis mode. The manual warns of high ' +
        'rear-wheel current and a locked-rotor alarm after about 5 seconds, so the ' +
        'vehicle interface stops a spin at 5 s. Use it as a manoeuvre, not a driving mode.', 'warn')
            : '<p class="muted">Front wheels steer; minimum turning radius 1.36 m. The ' +
              'robot must be moving to turn.</p>') +
    '<div style="text-align:center;margin-top:18px">' +
    '<button class="estop" data-act="estop">E-STOP</button></div>' +
    '<div class="btnrow" style="justify-content:center">' +
    '<button class="act ' + (armed ? 'stop' : 'go') + '" data-act="remote_toggle"' +
      (ready ? '' : ' disabled') + '>' + (armed ? 'Disarm' : 'Arm remote drive') + '</button>' +
    '</div></div>';

  out += '</div>';
  return out;
}

function render() {
  const main = document.getElementById('main');
  renderSubtabs();

  // The problems rail belongs to Autoware's health view; elsewhere it is noise.
  const railCard = document.getElementById('rail-card');
  const wantRail = (S.tab === 'autoware' && (S.sub === 'health' || S.sub === 'events'));
  if (railCard) railCard.style.display = wantRail ? '' : 'none';

  if (S.tab === 'hardware') {
    main.innerHTML = (S.sub === 'chassis') ? renderChassis() : renderDevices();
  } else if (S.tab === 'foxglove') {
    main.innerHTML = renderFoxgloveTab();
  } else if (S.tab === 'autoware') {
    if (S.sub === 'run') main.innerHTML = renderAutowareRun();
    else if (S.sub === 'goals') main.innerHTML = renderGoals();
    else if (S.sub === 'events') main.innerHTML = renderEvents();
    else if (S.view === 'module' && S.stream) main.innerHTML = renderModule();
    else main.innerHTML = renderOverview();
  } else if (S.tab === 'remote') {
    main.innerHTML = renderRemote();
  }

  renderHeader();
  renderRail();
  document.querySelectorAll('nav.tabs button').forEach(function (b) {
    b.classList.toggle('on', b.dataset.tab === S.tab);
  });
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

// Which pollers each tab needs. Polling only while a tab is open keeps a tablet
// left on the Foxglove tab from waking the ROS bridge every second.
function pollFor(tab, sub) {
  if (tab === 'hardware') { (sub === 'chassis') ? pollVehicle() : pollDevices(); }
  else if (tab === 'foxglove') pollFoxglove();
  else if (tab === 'autoware' || tab === 'remote') { pollControl(); pollVehicle(); }
}

document.addEventListener('click', (e) => {
  const tab = e.target.closest('nav.tabs button');
  if (tab) {
    S.tab = tab.dataset.tab;
    const subs = (TABS[S.tab] || {}).subs || [];
    S.sub = subs.length ? subs[0][0] : null;
    if (S.tab === 'autoware' && S.sub === 'health') S.view = 'overview';
    pollFor(S.tab, S.sub);
    render();
    return;
  }

  const sub = e.target.closest('nav.subtabs button');
  if (sub) {
    S.sub = sub.dataset.sub;
    if (S.tab === 'autoware') S.view = (S.sub === 'events') ? 'events' : 'overview';
    pollFor(S.tab, S.sub);
    render();
    return;
  }

  // Every write goes to the control backend. This process cannot perform any of them.
  const act = e.target.closest('[data-act]');
  if (act) { doAction(act.dataset.act, act); return; }

  const nav = e.target.closest('nav button');
  if (nav && nav.dataset.view) {
    S.view = nav.dataset.view;
    if (S.view === 'devices') pollDevices();
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

// --------------------------------------------------- control backend bridge
// Everything that can change the vehicle lives in a separate process on 8843.
// If it is not running the UI still works; the control tabs say so.
const CTRL = () => location.protocol + '//' + location.hostname + ':8843';

let ctrlTimer = null;
async function pollControl() {
  try {
    const r = await fetch(CTRL() + '/api/state', { signal: AbortSignal.timeout(2000) });
    S.autoware = await r.json();
    S.ctrl = { up: true };
  } catch (e) {
    S.ctrl = { up: false };
    S.autoware = S.autoware || {};
  }
  updateFoxButton();
  const dot = document.getElementById('ctrl-dot');
  const txt = document.getElementById('ctrl-text');
  if (dot) dot.className = 'dot' + (S.ctrl.up ? ' ok' : '');
  if (txt) txt.textContent = S.ctrl.up ? 'control ready' : 'control offline';
  if (S.tab === 'autoware' || S.tab === 'remote') render();
  clearTimeout(ctrlTimer);
  if (S.tab === 'autoware' || S.tab === 'remote') ctrlTimer = setTimeout(pollControl, 2000);
}

const CONFIRM = {
  autoware_start: 'Start Autoware?',
  autoware_stop: 'Stop Autoware?',
  engage: 'ENGAGE — the vehicle will begin to move. Continue?',
  mode_auto: 'Switch to AUTONOMOUS? This enables the motors.',
  remote_toggle: 'Toggle remote drive?',
  run_goals: 'Run the destination sequence? The vehicle will move.',
};

async function doAction(name, el) {
  // Anything that can cause motion asks first. The e-stop never does: a confirm
  // dialog between the operator and stopping the robot is the wrong trade.
  if (CONFIRM[name] && !confirm(CONFIRM[name])) return;
  if (el) el.disabled = true;
  try {
    const r = await fetch(CTRL() + '/api/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: name }),
    });
    const j = await r.json();
    if (!j.ok) alert('Failed: ' + (j.error || 'unknown'));
  } catch (e) {
    alert('Control backend unreachable: ' + e);
  } finally {
    if (el) el.disabled = false;
    pollControl();
  }
}

// The header button deep-links Foxglove with the bridge address already filled
// in: app.foxglove.dev honours ds=foxglove-websocket&ds.url=, which saves typing
// a ws:// URL on a tablet. Disabled while the bridge is down, because a link
// that opens Foxglove onto nothing is worse than a greyed-out one.
function updateFoxButton() {
  const a = document.getElementById('fox-btn');
  if (!a) return;
  const f = S.foxglove;
  const up = f && f.bridge_running;
  const ws = 'ws://' + location.hostname + ':' + ((f && f.bridge_port) || 8765);
  if (up) {
    a.className = 'fox-btn';
    a.href = 'https://app.foxglove.dev/~/view?ds=foxglove-websocket&ds.url=' +
             encodeURIComponent(ws);
    a.title = 'open Foxglove connected to ' + ws;
  } else {
    a.className = 'fox-btn down';
    a.removeAttribute('href');
    a.title = 'the Foxglove bridge is not running';
  }
}

// ------------------------------------------------------- hold-to-drive input
// The knob position is the command: y is throttle, x is steering, both -1..1.
// Nothing latches. Releasing, leaving the pad, hiding the tab or losing the
// network all stop the robot, because the vehicle interface zeroes the command
// 0.5 s after the last one arrives. That watchdog is the real safety mechanism;
// this UI is built to feed it, not to replace it.
let driveTimer = null;
let joyActive = false;
let joyX = 0, joyY = 0;

function joySend() {
  const spd = parseFloat((document.getElementById('spd') || {}).value || '0.5');
  // Dead zone: a thumb resting on the knob should not creep the robot.
  const mag = Math.hypot(joyX, joyY);
  let dir = 'stop', speed = 0, turn = 0;
  if (mag > 0.18) {
    turn = -joyX;                       // screen x is rightward; steering is leftward
    if (Math.abs(joyY) > 0.18) {
      dir = joyY < 0 ? 'fwd' : 'back';
      speed = spd * Math.min(1, Math.abs(joyY));
    } else {
      dir = joyX < 0 ? 'left' : 'right';
      speed = spd;
    }
  }
  fetch(CTRL() + '/api/drive', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dir: dir, speed: speed, turn: turn }),
  }).catch(joyStop);
}

function joyMove(e) {
  const pad = document.getElementById('pad');
  if (!pad || !joyActive) return;
  const b = pad.getBoundingClientRect();
  const cx = b.left + b.width / 2, cy = b.top + b.height / 2;
  const rad = b.width / 2 * 0.68;
  let dx = (e.clientX - cx) / rad, dy = (e.clientY - cy) / rad;
  const m = Math.hypot(dx, dy);
  if (m > 1) { dx /= m; dy /= m; }
  joyX = dx; joyY = dy;
  const k = document.getElementById('knob');
  if (k) k.style.transform = 'translate(calc(-50% + ' + (dx * rad) + 'px), calc(-50% + ' + (dy * rad) + 'px))';
}

function joyStart(e) {
  const pad = document.getElementById('pad');
  if (!pad || pad.classList.contains('disabled')) return;
  joyActive = true;
  pad.classList.add('active');
  joyMove(e);
  clearInterval(driveTimer);
  driveTimer = setInterval(joySend, 100);
  joySend();
}

function joyStop() {
  if (!joyActive) return;
  joyActive = false; joyX = 0; joyY = 0;
  clearInterval(driveTimer); driveTimer = null;
  const pad = document.getElementById('pad');
  const k = document.getElementById('knob');
  if (pad) pad.classList.remove('active');
  if (k) k.style.transform = 'translate(-50%, -50%)';
  fetch(CTRL() + '/api/drive', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dir: 'stop', speed: 0, turn: 0 }),
  }).catch(function () {});
}

document.addEventListener('pointerdown', function (e) {
  if (e.target.closest('#pad')) { e.preventDefault(); joyStart(e); }
});
document.addEventListener('pointermove', function (e) { if (joyActive) joyMove(e); });
['pointerup', 'pointercancel'].forEach(function (ev) {
  document.addEventListener(ev, joyStop);
});
window.addEventListener('blur', joyStop);
document.addEventListener('visibilitychange', function () { if (document.hidden) joyStop(); });
window.addEventListener('pagehide', joyStop);

document.addEventListener('input', function (e) {
  if (e.target && e.target.id === 'spd') {
    const el = document.getElementById('spdv');
    if (el) el.textContent = e.target.value + ' m/s';
  }
});
document.addEventListener('change', function (e) {
  if (e.target && e.target.id === 'spd') {
    fetch(CTRL() + '/api/action', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'set_max_speed', value: parseFloat(e.target.value) }),
    }).catch(function () {});
  }
});

let devTimer = null;
async function pollDevices() {
  const r = await fetch('/api/devices');
  S.devices = await r.json();
  if (S.view === 'devices') render();
  clearTimeout(devTimer);
  if (S.view === 'devices') devTimer = setTimeout(pollDevices, 3000);
}

pollFor(S.tab, S.sub);
pollControl();
pollFoxglove();

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
