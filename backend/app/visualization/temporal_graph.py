"""
Temporal graph visualization — HTML with Vis.js + date slider.
"""
from __future__ import annotations

import json
from datetime import date

from app.services.journal_ops import journal_ops

# Domain → color mapping
DOMAIN_COLORS = {
    "career": "#4A90D9",
    "wealth": "#50C878",
    "love": "#E74C3C",
    "social": "#F39C12",
    "study": "#9B59B6",
    "general": "#95A5A6",
}

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<title>Journal Graph — Temporal View</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  body {{ margin: 0; font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee; }}
  #controls {{ padding: 12px 20px; background: #16213e; display: flex; align-items: center; gap: 16px; }}
  #controls label {{ font-size: 14px; }}
  #date-slider {{ flex: 1; }}
  #date-slider:focus {{ outline: 2px solid #4A90D9; outline-offset: 2px; }}
  #date-slider:focus:not(:focus-visible) {{ outline: none; }}
  #date-display {{ font-weight: bold; min-width: 100px; }}
  #legend {{ display: flex; gap: 12px; }}
  .legend-item {{ display: flex; align-items: center; gap: 4px; font-size: 12px; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  #graph {{ width: 100%; height: calc(100vh - 50px); }}
</style>
</head>
<body>
<div id="controls" role="toolbar" aria-label="Timeline controls">
  <label for="date-slider">Date:</label>
  <input type="range" id="date-slider" min="0" max="0" value="0"
         aria-label="Timeline date selector">
  <span id="date-display" aria-live="polite">—</span>
  <div id="legend" aria-label="Domain color legend">
    <div class="legend-item"><div class="legend-dot" style="background:#4A90D9" aria-hidden="true"></div>career</div>
    <div class="legend-item"><div class="legend-dot" style="background:#50C878" aria-hidden="true"></div>wealth</div>
    <div class="legend-item"><div class="legend-dot" style="background:#E74C3C" aria-hidden="true"></div>love</div>
    <div class="legend-item"><div class="legend-dot" style="background:#F39C12" aria-hidden="true"></div>social</div>
    <div class="legend-item"><div class="legend-dot" style="background:#9B59B6" aria-hidden="true"></div>study</div>
    <div class="legend-item"><div class="legend-dot" style="background:#95A5A6" aria-hidden="true"></div>general</div>
  </div>
</div>
<div id="graph" role="img" aria-label="Journal knowledge graph visualization"></div>
<script>
const SNAPSHOTS = {snapshots_json};
const DOMAIN_COLORS = {domain_colors_json};

const container = document.getElementById('graph');
const slider = document.getElementById('date-slider');
const dateDisplay = document.getElementById('date-display');

slider.max = Math.max(0, SNAPSHOTS.length - 1);

let network = null;

function renderSnapshot(idx) {{
  if (idx >= SNAPSHOTS.length) return;
  const snap = SNAPSHOTS[idx];
  dateDisplay.textContent = snap.date;
  slider.setAttribute('aria-valuetext', snap.date);

  const data = snap.data;
  const nodes = (data.items || []).map(item => ({{
    id: item.id,
    label: item.title,
    color: {{
      background: DOMAIN_COLORS[item.domain] || '#95A5A6',
      border: item.above_floor ? '#fff' : '#555',
    }},
    size: 10 + Math.min(item.raw_score * 10, 40),
    font: {{ color: '#eee', size: 12 }},
    opacity: item.above_floor ? 1.0 : 0.3,
  }}));

  const edges = (data.edges || []).map(e => ({{
    from: e.source_id,
    to: e.target_id,
    label: e.relation,
    width: Math.max(1, e.strength * 2),
    color: {{ color: 'rgba(255,255,255,0.3)' }},
    font: {{ color: '#888', size: 9 }},
  }}));

  if (network) {{
    network.setData({{ nodes, edges }});
  }} else {{
    network = new vis.Network(container, {{ nodes, edges }}, {{
      physics: {{ solver: 'forceAtlas2Based', forceAtlas2Based: {{ gravitationalConstant: -50 }} }},
      interaction: {{ hover: true, tooltipDelay: 100 }},
      edges: {{ smooth: {{ type: 'continuous' }} }},
    }});
  }}
}}

slider.addEventListener('input', () => renderSnapshot(parseInt(slider.value)));
if (SNAPSHOTS.length > 0) renderSnapshot(0);
</script>
</body>
</html>
"""


class TemporalGraphVisualizer:
    def __init__(self, user_id: str):
        self.user_id = user_id

    def render_html(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> str:
        """Generate HTML with temporal slider."""
        snapshots_raw = journal_ops.get_snapshots(
            self.user_id,
            start_date.isoformat() if start_date else None,
            end_date.isoformat() if end_date else None,
        )

        snapshots = []
        for s in snapshots_raw:
            snapshots.append({
                "date": s["snapshot_date"],
                "data": s["snapshot_data"],
            })

        return HTML_TEMPLATE.format(
            snapshots_json=json.dumps(snapshots, default=str),
            domain_colors_json=json.dumps(DOMAIN_COLORS),
        )

    def render(
        self,
        output_path: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        """Write HTML file and return metadata."""
        html = self.render_html(start_date, end_date)
        with open(output_path, "w") as f:
            f.write(html)
        return {"path": output_path, "snapshots_count": html.count('"date"')}
