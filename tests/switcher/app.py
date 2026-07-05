"""
AI Benchmark Switcher — compare all 6 implementations side by side
Run: python app.py (port 8090)
"""
from flask import Flask, render_template_string

app = Flask(__name__)

TOOLS = [
    {
        "id": "bmad_v4",
        "name": "BMAD v4",
        "subtitle": "GitHub Copilot + BMAD Method",
        "port": 8080,
        "score": 30,
        "color": "#6366f1",
        "tags": ["Copilot", "No API cost"],
        "verdict": "Solid baseline. Best dark UI but needed 3 manual fixes before running.",
    },
    {
        "id": "traycer",
        "name": "Traycer.ai",
        "subtitle": "Traycer + Claude Code",
        "port": 8081,
        "score": 32,
        "color": "#0ea5e9",
        "tags": ["Claude Code", "Best planning"],
        "verdict": "Best pre-build review — caught division-by-zero. API reliability issues hurt.",
    },
    {
        "id": "amp",
        "name": "Amp",
        "subtitle": "Amp terminal agent",
        "port": 8082,
        "score": 32,
        "color": "#10b981",
        "tags": ["$0.20", "Fastest", "Self-tested"],
        "verdict": "Fastest at 3–5 min for $0.20. Self-tested output. Plain frontend.",
    },
    {
        "id": "superpowers",
        "name": "Superpowers",
        "subtitle": "Superpowers + Claude Code",
        "port": 8083,
        "score": 35,
        "color": "#f59e0b",
        "tags": ["Claude Code", "TDD", "Best output"],
        "verdict": "Best output — sortable table, 11 unit tests, 4 bugs self-caught. Slowest.",
    },
    {
        "id": "ralph",
        "name": "Ralph",
        "subtitle": "Ralph + Claude Code",
        "port": 8084,
        "score": 8,
        "color": "#ef4444",
        "tags": ["Claude Code", "Autonomous loop"],
        "verdict": "Circuit breaker opened — never produced a working app. Wrong tool for this.",
    },
    {
        "id": "bmad_v6",
        "name": "BMAD v6",
        "subtitle": "BMAD v6 + Copilot (Claude Sonnet 4.6)",
        "port": 8085,
        "score": 30,
        "color": "#8b5cf6",
        "tags": ["Copilot", "No API cost", "Agent mode"],
        "verdict": "Zero cost upgrade over v4. Autonomous error recovery. No sortable columns.",
    },
]

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Benchmark — Tool Switcher</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #09090b;
      --surface: #111113;
      --border: #27272a;
      --text: #fafafa;
      --muted: #71717a;
      --accent: #f59e0b;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'DM Sans', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }

    /* ── Header ── */
    header {
      border-bottom: 1px solid var(--border);
      padding: 20px 32px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      background: rgba(9,9,11,0.92);
      backdrop-filter: blur(12px);
      z-index: 100;
    }

    .logo {
      font-family: 'Space Mono', monospace;
      font-size: 0.9rem;
      color: var(--accent);
      letter-spacing: 0.08em;
    }

    .logo span { color: var(--muted); }

    .header-meta {
      font-size: 0.75rem;
      color: var(--muted);
      font-family: 'Space Mono', monospace;
    }

    /* ── Tool nav tabs ── */
    .tool-nav {
      display: flex;
      gap: 4px;
      padding: 16px 32px;
      border-bottom: 1px solid var(--border);
      overflow-x: auto;
      scrollbar-width: none;
    }

    .tool-nav::-webkit-scrollbar { display: none; }

    .tool-tab {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      padding: 10px 16px;
      border-radius: 8px;
      border: 1px solid var(--border);
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
      background: transparent;
      color: var(--text);
      text-align: left;
      min-width: 140px;
    }

    .tool-tab:hover {
      border-color: var(--accent);
      background: rgba(245,158,11,0.05);
    }

    .tool-tab.active {
      background: rgba(245,158,11,0.1);
      border-color: var(--accent);
    }

    .tab-name {
      font-weight: 600;
      font-size: 0.9rem;
    }

    .tab-score {
      font-family: 'Space Mono', monospace;
      font-size: 0.75rem;
      margin-top: 2px;
    }

    .score-bar {
      width: 100%;
      height: 3px;
      background: var(--border);
      border-radius: 2px;
      margin-top: 6px;
      overflow: hidden;
    }

    .score-fill {
      height: 100%;
      border-radius: 2px;
      transition: width 0.3s;
    }

    /* ── Main layout ── */
    .main {
      display: grid;
      grid-template-columns: 320px 1fr;
      height: calc(100vh - 130px);
    }

    /* ── Sidebar ── */
    .sidebar {
      border-right: 1px solid var(--border);
      padding: 24px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    .sidebar-section h3 {
      font-family: 'Space Mono', monospace;
      font-size: 0.65rem;
      color: var(--muted);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }

    .score-display {
      display: flex;
      align-items: baseline;
      gap: 6px;
    }

    .score-big {
      font-family: 'Space Mono', monospace;
      font-size: 2.8rem;
      font-weight: 700;
      line-height: 1;
    }

    .score-denom {
      font-family: 'Space Mono', monospace;
      font-size: 1rem;
      color: var(--muted);
    }

    .tool-title {
      font-size: 1.3rem;
      font-weight: 600;
      margin-bottom: 4px;
    }

    .tool-subtitle {
      font-size: 0.8rem;
      color: var(--muted);
      margin-bottom: 12px;
    }

    .tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 16px;
    }

    .tag {
      font-size: 0.7rem;
      padding: 3px 8px;
      border-radius: 4px;
      border: 1px solid var(--border);
      color: var(--muted);
      font-family: 'Space Mono', monospace;
    }

    .verdict-text {
      font-size: 0.85rem;
      color: #a1a1aa;
      line-height: 1.6;
    }

    .port-info {
      font-family: 'Space Mono', monospace;
      font-size: 0.75rem;
      color: var(--muted);
      padding: 10px 12px;
      background: var(--surface);
      border-radius: 6px;
      border: 1px solid var(--border);
    }

    .port-info a {
      color: var(--accent);
      text-decoration: none;
    }

    .port-info a:hover { text-decoration: underline; }

    /* ── Criteria bars ── */
    .criteria-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .criteria-row {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .criteria-label {
      font-size: 0.75rem;
      color: var(--muted);
      width: 110px;
      flex-shrink: 0;
    }

    .criteria-bar-bg {
      flex: 1;
      height: 6px;
      background: var(--border);
      border-radius: 3px;
      overflow: hidden;
    }

    .criteria-bar-fill {
      height: 100%;
      border-radius: 3px;
      transition: width 0.4s ease;
    }

    .criteria-val {
      font-family: 'Space Mono', monospace;
      font-size: 0.7rem;
      color: var(--muted);
      width: 20px;
      text-align: right;
    }

    /* ── Preview pane ── */
    .preview-pane {
      display: flex;
      flex-direction: column;
    }

    .preview-header {
      padding: 12px 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--surface);
    }

    .preview-url {
      font-family: 'Space Mono', monospace;
      font-size: 0.75rem;
      color: var(--muted);
    }

    .preview-status {
      font-family: 'Space Mono', monospace;
      font-size: 0.7rem;
      padding: 3px 8px;
      border-radius: 4px;
      background: rgba(16,185,129,0.1);
      color: #10b981;
      border: 1px solid rgba(16,185,129,0.2);
    }

    .preview-status.offline {
      background: rgba(239,68,68,0.1);
      color: #ef4444;
      border-color: rgba(239,68,68,0.2);
    }

    iframe {
      flex: 1;
      border: none;
      background: white;
    }

    .iframe-placeholder {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 12px;
      color: var(--muted);
      font-family: 'Space Mono', monospace;
      font-size: 0.8rem;
    }

    .iframe-placeholder .big {
      font-size: 2rem;
    }

    /* ── Compare view ── */
    .compare-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1px;
      background: var(--border);
      flex: 1;
    }

    .compare-cell {
      background: var(--bg);
      display: flex;
      flex-direction: column;
    }

    .compare-cell-header {
      padding: 8px 12px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      font-size: 0.75rem;
      font-weight: 600;
      display: flex;
      justify-content: space-between;
    }

    .compare-cell iframe {
      flex: 1;
    }

    /* ── View toggle ── */
    .view-toggle {
      display: flex;
      gap: 4px;
    }

    .view-btn {
      padding: 5px 12px;
      border-radius: 5px;
      border: 1px solid var(--border);
      background: transparent;
      color: var(--muted);
      font-size: 0.75rem;
      cursor: pointer;
      font-family: 'Space Mono', monospace;
      transition: all 0.15s;
    }

    .view-btn:hover, .view-btn.active {
      background: var(--surface);
      color: var(--text);
      border-color: var(--accent);
    }

    /* ── Responsive ── */
    @media (max-width: 900px) {
      .main { grid-template-columns: 1fr; height: auto; }
      .sidebar { border-right: none; border-bottom: 1px solid var(--border); max-height: none; }
      .compare-grid { grid-template-columns: 1fr; }
      iframe { min-height: 420px; }
      .compare-cell iframe { min-height: 320px; }
    }

    @media (max-width: 600px) {
      header { padding: 12px 16px; flex-wrap: wrap; gap: 6px; }
      .logo { font-size: 0.75rem; }
      .header-meta { font-size: 0.65rem; }

      .tool-nav { padding: 10px 12px; gap: 6px; }
      .tool-tab { min-width: 100px; padding: 8px 10px; }
      .tab-name { font-size: 0.8rem; }
      .tab-score { font-size: 0.68rem; }

      .sidebar { padding: 16px; gap: 14px; }
      .score-big { font-size: 2rem; }
      .tool-title { font-size: 1.1rem; }
      .criteria-label { width: 90px; font-size: 0.7rem; }

      .preview-header { padding: 8px 12px; flex-wrap: wrap; gap: 6px; }
      .preview-url { font-size: 0.65rem; word-break: break-all; }
      .view-btn { padding: 4px 8px; font-size: 0.7rem; }
      .preview-status { font-size: 0.65rem; }

      iframe { min-height: 360px; }
      .compare-grid { grid-template-columns: 1fr; }
      .compare-cell iframe { min-height: 280px; }

      .main { height: auto; }
    }
  </style>
</head>
<body>

<header>
  <div class="logo">AI<span>/</span>BENCHMARK <span>— Basketball Stats Analyzer</span></div>
  <div class="header-meta">6 tools · April 2026 · Neil Mahajan</div>
</header>

<!-- Tool tabs -->
<div class="tool-nav" id="toolNav">
  {% for tool in tools %}
  <button class="tool-tab {% if loop.first %}active{% endif %}"
          onclick="selectTool('{{ tool.id }}')"
          id="tab-{{ tool.id }}"
          data-id="{{ tool.id }}">
    <span class="tab-name">{{ tool.name }}</span>
    <span class="tab-score" style="color: {{ tool.color }}">{{ tool.score }}/40</span>
    <div class="score-bar">
      <div class="score-fill" style="width: {{ (tool.score / 40 * 100)|int }}%; background: {{ tool.color }}"></div>
    </div>
  </button>
  {% endfor %}
</div>

<div class="main" id="mainLayout">
  <!-- Sidebar -->
  <div class="sidebar" id="sidebar">
    {% for tool in tools %}
    <div class="tool-detail" id="detail-{{ tool.id }}" style="display: {% if loop.first %}block{% else %}none{% endif %}">

      <div class="sidebar-section">
        <h3>Tool</h3>
        <div class="tool-title">{{ tool.name }}</div>
        <div class="tool-subtitle">{{ tool.subtitle }}</div>
        <div class="tags">
          {% for tag in tool.tags %}
          <span class="tag">{{ tag }}</span>
          {% endfor %}
        </div>
      </div>

      <div class="sidebar-section">
        <h3>Score</h3>
        <div class="score-display">
          <span class="score-big" style="color: {{ tool.color }}">{{ tool.score }}</span>
          <span class="score-denom">/40</span>
        </div>
      </div>

      <div class="sidebar-section">
        <h3>Criteria</h3>
        <div class="criteria-list" id="criteria-{{ tool.id }}"></div>
      </div>

      <div class="sidebar-section">
        <h3>Verdict</h3>
        <p class="verdict-text">{{ tool.verdict }}</p>
      </div>

      <div class="sidebar-section">
        <h3>Local Server</h3>
        <div class="port-info">
          Port {{ tool.port }} →
          <a href="http://127.0.0.1:{{ tool.port }}" target="_blank">
            127.0.0.1:{{ tool.port }}
          </a>
        </div>
      </div>

    </div>
    {% endfor %}
  </div>

  <!-- Preview pane -->
  <div class="preview-pane" id="previewPane">
    <div class="preview-header">
      <span class="preview-url" id="previewUrl">http://127.0.0.1:8080</span>
      <div style="display:flex; gap:8px; align-items:center">
        <div class="view-toggle">
          <button class="view-btn active" onclick="setView('single')" id="btnSingle">Single</button>
          <button class="view-btn" onclick="setView('compare')" id="btnCompare">Compare All</button>
        </div>
        <span class="preview-status" id="previewStatus">LIVE</span>
      </div>
    </div>

    <!-- Single view -->
    <div id="singleView" style="display:flex; flex:1; flex-direction:column;">
      <iframe id="mainFrame" src="http://127.0.0.1:8080"
              onerror="markOffline()"
              onload="markOnline()"></iframe>
    </div>

    <!-- Compare view (hidden by default) -->
    <div id="compareView" style="display:none; flex:1;" class="compare-grid">
      {% for tool in tools %}
      <div class="compare-cell">
        <div class="compare-cell-header">
          <span style="color:{{ tool.color }}">{{ tool.name }}</span>
          <span style="color:#71717a; font-family:'Space Mono',monospace">{{ tool.score }}/40</span>
        </div>
        <iframe src="http://127.0.0.1:{{ tool.port }}"
                title="{{ tool.name }}"></iframe>
      </div>
      {% endfor %}
    </div>
  </div>
</div>

<script>
  const tools = {{ tools | tojson }};

  const CRITERIA = [
    'Planning', 'Speed', 'Data Handling',
    'Math Accuracy', 'Frontend Quality',
    'File Structure', 'Error Recovery', 'Overall Experience'
  ];

  // Scores per tool per criteria
  const SCORES = {
    bmad_v4:     [2, 3, 5, 5, 5, 4, 3, 3],
    traycer:     [5, 2, 5, 5, 5, 5, 2, 3],
    amp:         [2, 5, 5, 5, 2, 3, 5, 5],
    superpowers: [5, 1, 5, 5, 5, 5, 5, 4],
    ralph:       [1, 1, 0, 0, 2, 2, 1, 1],
    bmad_v6:     [3, 4, 4, 4, 4, 4, 4, 3],
  };

  function buildCriteria(toolId, color) {
    const container = document.getElementById('criteria-' + toolId);
    if (container.children.length > 0) return;
    const scores = SCORES[toolId];
    scores.forEach((score, i) => {
      const pct = score === 0 ? 0 : (score / 5 * 100);
      const row = document.createElement('div');
      row.className = 'criteria-row';
      row.innerHTML = `
        <span class="criteria-label">${CRITERIA[i]}</span>
        <div class="criteria-bar-bg">
          <div class="criteria-bar-fill" style="width:${pct}%; background:${color}"></div>
        </div>
        <span class="criteria-val">${score === 0 ? 'N/A' : score}</span>
      `;
      container.appendChild(row);
    });
  }

  let currentTool = 'bmad_v4';
  let currentView = 'single';

  function selectTool(id) {
    // Hide all details
    document.querySelectorAll('.tool-detail').forEach(d => d.style.display = 'none');
    document.querySelectorAll('.tool-tab').forEach(t => t.classList.remove('active'));

    // Show selected
    document.getElementById('detail-' + id).style.display = 'block';
    document.getElementById('tab-' + id).classList.add('active');

    const tool = tools.find(t => t.id === id);
    const url = 'http://127.0.0.1:' + tool.port;

    document.getElementById('previewUrl').textContent = url;
    document.getElementById('mainFrame').src = url;

    buildCriteria(id, tool.color);
    currentTool = id;
  }

  function setView(view) {
    currentView = view;
    const isMobile = window.innerWidth <= 900;
    if (view === 'single') {
      document.getElementById('singleView').style.display = 'flex';
      document.getElementById('compareView').style.display = 'none';
      document.getElementById('sidebar').style.display = 'flex';
      document.getElementById('btnSingle').classList.add('active');
      document.getElementById('btnCompare').classList.remove('active');
      document.getElementById('mainLayout').style.gridTemplateColumns = isMobile ? '1fr' : '320px 1fr';
    } else {
      document.getElementById('singleView').style.display = 'none';
      document.getElementById('compareView').style.display = 'grid';
      document.getElementById('sidebar').style.display = 'none';
      document.getElementById('btnCompare').classList.add('active');
      document.getElementById('btnSingle').classList.remove('active');
      document.getElementById('mainLayout').style.gridTemplateColumns = '1fr';
    }
  }

  window.addEventListener('resize', () => {
    if (currentView === 'single') {
      document.getElementById('mainLayout').style.gridTemplateColumns =
        window.innerWidth <= 900 ? '1fr' : '320px 1fr';
    }
  });

  function markOnline() {
    const el = document.getElementById('previewStatus');
    el.textContent = 'LIVE';
    el.className = 'preview-status';
  }

  function markOffline() {
    const el = document.getElementById('previewStatus');
    el.textContent = 'OFFLINE';
    el.className = 'preview-status offline';
  }

  // Build criteria for first tool on load
  buildCriteria('bmad_v4', tools[0].color);
</script>

</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML, tools=TOOLS)

if __name__ == "__main__":
    app.run(port=8090, debug=True)
