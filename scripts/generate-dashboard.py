#!/usr/bin/env python3
"""
Generate Dashboard — Build a self-contained HTML dashboard of application stats.

Output: docs/index.html (or --output-dir)

Features:
  - Funnel doughnut chart (stages)
  - ATS scores bar chart
  - Applications per month bar chart
  - Active applications table

Usage:
    scripts/generate-dashboard.py [--output-dir DIR] [--no-gh] [--json-data]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from lib.common import REPO_ROOT, require_yaml

yaml = require_yaml()


# ── Data collection ────────────────────────────────────────────────────────────

def get_pr_info(name: str) -> dict:
    """Query GitHub CLI for PR info on an apply/* branch."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--head", f"apply/{name}", "--state", "all",
             "--json", "state,url,labels,createdAt,mergedAt",
             "--jq", "if length > 0 then .[0] | tojson else \"\" end"],
            capture_output=True, text=True, timeout=10, cwd=REPO_ROOT,
        )
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
    except Exception:
        pass
    return {}


def get_ats_score(app_dir: Path) -> float | None:
    """Run ats-score.py and return score or None."""
    job_path = app_dir / "job.txt"
    if not job_path.exists():
        return None
    try:
        result = subprocess.run(
            ["python3", "scripts/ats-score.py", str(app_dir), "--json"],
            capture_output=True, text=True, timeout=20, cwd=REPO_ROOT,
        )
        if result.returncode in (0, 1) and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            return round(data.get("score", 0), 1)
    except Exception:
        pass
    return None


def get_stage(pr: dict, meta: dict) -> str:
    """Derive funnel stage from PR labels and meta outcome."""
    outcome = meta.get("outcome", "")
    if outcome == "interview":
        return "Interview"
    if outcome == "offer":
        return "Offer"
    if outcome in ("rejected", "ghosted"):
        return "Rejected"
    if not pr:
        return "Draft"
    labels = [la.get("name", "") for la in pr.get("labels", [])]
    if "status:offer" in labels:
        return "Offer"
    if "status:interview" in labels:
        return "Interview"
    if "status:rejected" in labels:
        return "Rejected"
    if pr.get("state") in ("MERGED", "OPEN"):
        return "Applied"
    return "Draft"


def collect_data(no_gh: bool = False) -> dict:
    """Collect all application data."""
    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.exists():
        return {"applications": [], "generated": str(date.today())}

    today = date.today()
    apps = []

    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        meta_path = app_dir / "meta.yml"
        if not meta_path.exists():
            continue

        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
        except Exception:
            continue

        name = app_dir.name
        company = meta.get("company", name)
        position = meta.get("position", "")
        created_raw = meta.get("created", "")

        # Parse created date
        created = None
        if created_raw:
            for fmt in ("%Y-%m-%d", "%Y-%m"):
                try:
                    created = datetime.strptime(str(created_raw), fmt).date()
                    break
                except ValueError:
                    pass

        # Days since created
        days_since = (today - created).days if created else None

        # PR info
        pr = {}
        if not no_gh:
            pr = get_pr_info(name)

        stage = get_stage(pr, meta)

        # ATS score (only if job.txt exists)
        ats_score = get_ats_score(app_dir)

        apps.append({
            "name": name,
            "company": company,
            "position": position,
            "created": str(created) if created else "",
            "created_month": created.strftime("%Y-%m") if created else "",
            "stage": stage,
            "ats_score": ats_score,
            "days_since": days_since,
            "pr_url": pr.get("url", ""),
            "outcome": meta.get("outcome", ""),
        })

    # Stats
    total = len(apps)
    by_stage: dict = {}
    for app in apps:
        s = app["stage"]
        by_stage[s] = by_stage.get(s, 0) + 1

    interview_count = by_stage.get("Interview", 0) + by_stage.get("Offer", 0)
    applied_count = total - by_stage.get("Draft", 0)
    interview_rate = round(interview_count / applied_count * 100, 1) if applied_count > 0 else 0

    scored_apps = [a for a in apps if a["ats_score"] is not None]
    avg_ats = round(sum(a["ats_score"] for a in scored_apps) / len(scored_apps), 1) if scored_apps else None

    # Monthly breakdown
    monthly: dict = {}
    for app in apps:
        m = app["created_month"]
        if m:
            monthly[m] = monthly.get(m, 0) + 1

    return {
        "applications": apps,
        "stats": {
            "total": total,
            "by_stage": by_stage,
            "interview_rate_pct": interview_rate,
            "avg_ats_score": avg_ats,
            "in_progress": by_stage.get("Applied", 0) + by_stage.get("Interview", 0),
        },
        "monthly": monthly,
        "generated": str(date.today()),
    }


# ── HTML generation ────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CV Application Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0f172a;
    --surface: #1e293b;
    --surface2: #263045;
    --border: #334155;
    --text: #f1f5f9;
    --text2: #94a3b8;
    --accent: #3b82f6;
    --green: #22c55e;
    --yellow: #eab308;
    --orange: #f97316;
    --red: #ef4444;
    --purple: #a855f7;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.5;
    padding: 24px;
  }
  h1 { font-size: 1.5rem; font-weight: 700; }
  h2 { font-size: 1rem; font-weight: 600; color: var(--text2); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 16px; }
  header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border);
  }
  .meta { color: var(--text2); font-size: 12px; }
  .chips { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }
  .chip {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 12px 20px; min-width: 140px; text-align: center;
  }
  .chip .value { font-size: 1.75rem; font-weight: 700; color: var(--accent); }
  .chip .label { font-size: 12px; color: var(--text2); margin-top: 2px; }
  .charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 20px;
  }
  .chart-card { height: 320px; }
  .chart-card canvas { max-height: 260px; }
  .full-card { margin-bottom: 16px; }
  table { width: 100%; border-collapse: collapse; }
  th {
    text-align: left; padding: 8px 12px; font-size: 11px; font-weight: 600;
    color: var(--text2); text-transform: uppercase; letter-spacing: 0.05em;
    border-bottom: 1px solid var(--border);
  }
  td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--surface2); }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 600;
  }
  .badge-draft { background: #334155; color: #94a3b8; }
  .badge-applied { background: #1d4ed8; color: #bfdbfe; }
  .badge-interview { background: #a16207; color: #fef08a; }
  .badge-offer { background: #166534; color: #bbf7d0; }
  .badge-rejected { background: #7f1d1d; color: #fecaca; }
  .score-high { color: var(--green); font-weight: 600; }
  .score-mid { color: var(--yellow); font-weight: 600; }
  .score-low { color: var(--orange); font-weight: 600; }
  .score-poor { color: var(--red); font-weight: 600; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .ats-bar-wrap { width: 100%; height: 420px; overflow-y: auto; }
  @media (max-width: 768px) { .charts-row { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <div>
    <h1>📊 CV Application Dashboard</h1>
    <div class="meta" id="subtitle">Loading...</div>
  </div>
  <div class="meta" id="last-updated"></div>
</header>

<div class="chips" id="chips"></div>

<div class="charts-row">
  <div class="card chart-card">
    <h2>Funnel</h2>
    <canvas id="funnelChart"></canvas>
  </div>
  <div class="card chart-card">
    <h2>Applications per Month</h2>
    <canvas id="monthlyChart"></canvas>
  </div>
</div>

<div class="card full-card">
  <h2>ATS Scores by Application</h2>
  <div class="ats-bar-wrap">
    <canvas id="atsChart"></canvas>
  </div>
</div>

<div class="card full-card">
  <h2>All Applications</h2>
  <table id="appsTable">
    <thead>
      <tr>
        <th>Company</th>
        <th>Position</th>
        <th>Stage</th>
        <th>ATS</th>
        <th>Days</th>
        <th>Created</th>
      </tr>
    </thead>
    <tbody id="appsBody"></tbody>
  </table>
</div>

<script>
const DATA = __DATA__;

// ── Helpers ────────────────────────────────────────────────────────────────
function scoreClass(s) {
  if (s === null || s === undefined) return '';
  if (s >= 80) return 'score-high';
  if (s >= 60) return 'score-mid';
  if (s >= 40) return 'score-low';
  return 'score-poor';
}

function stageBadge(stage) {
  const map = {
    Draft: 'badge-draft',
    Applied: 'badge-applied',
    Interview: 'badge-interview',
    Offer: 'badge-offer',
    Rejected: 'badge-rejected',
  };
  const cls = map[stage] || 'badge-draft';
  return `<span class="badge ${cls}">${stage}</span>`;
}

// ── Header ─────────────────────────────────────────────────────────────────
document.getElementById('subtitle').textContent =
  `${DATA.stats.total} applications tracked`;
document.getElementById('last-updated').textContent =
  `Updated: ${DATA.generated}`;

// ── Chips ──────────────────────────────────────────────────────────────────
const chips = [
  { value: DATA.stats.total, label: 'Total' },
  { value: DATA.stats.in_progress, label: 'In Progress' },
  { value: DATA.stats.interview_rate_pct !== null ? DATA.stats.interview_rate_pct + '%' : '—', label: 'Interview Rate' },
  { value: DATA.stats.avg_ats_score !== null ? DATA.stats.avg_ats_score + '%' : '—', label: 'Avg ATS Score' },
];
const chipsEl = document.getElementById('chips');
chips.forEach(c => {
  const div = document.createElement('div');
  div.className = 'chip';
  div.innerHTML = `<div class="value">${c.value}</div><div class="label">${c.label}</div>`;
  chipsEl.appendChild(div);
});

// ── Funnel chart ───────────────────────────────────────────────────────────
const STAGE_ORDER = ['Draft', 'Applied', 'Interview', 'Offer', 'Rejected'];
const STAGE_COLORS = ['#475569', '#3b82f6', '#eab308', '#22c55e', '#ef4444'];
const funnelLabels = STAGE_ORDER.filter(s => DATA.stats.by_stage[s]);
const funnelValues = funnelLabels.map(s => DATA.stats.by_stage[s] || 0);
const funnelColors = funnelLabels.map(s => STAGE_COLORS[STAGE_ORDER.indexOf(s)]);

new Chart(document.getElementById('funnelChart'), {
  type: 'doughnut',
  data: {
    labels: funnelLabels,
    datasets: [{ data: funnelValues, backgroundColor: funnelColors, borderWidth: 2, borderColor: '#1e293b' }],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'right', labels: { color: '#f1f5f9', font: { size: 12 } } },
    },
  },
});

// ── Monthly chart ──────────────────────────────────────────────────────────
const months = Object.keys(DATA.monthly).sort();
const monthCounts = months.map(m => DATA.monthly[m]);

new Chart(document.getElementById('monthlyChart'), {
  type: 'bar',
  data: {
    labels: months,
    datasets: [{
      label: 'Applications',
      data: monthCounts,
      backgroundColor: '#3b82f6',
      borderRadius: 4,
    }],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
      y: { ticks: { color: '#94a3b8', stepSize: 1 }, grid: { color: '#334155' } },
    },
  },
});

// ── ATS scores chart ───────────────────────────────────────────────────────
const scoredApps = DATA.applications
  .filter(a => a.ats_score !== null && a.ats_score !== undefined)
  .sort((a, b) => b.ats_score - a.ats_score);

const atsHeight = Math.max(200, scoredApps.length * 32);
document.querySelector('.ats-bar-wrap').style.height = atsHeight + 'px';
const atsCanvas = document.getElementById('atsChart');
atsCanvas.style.height = (atsHeight - 20) + 'px';

function atsColor(score) {
  if (score >= 80) return '#22c55e';
  if (score >= 60) return '#eab308';
  if (score >= 40) return '#f97316';
  return '#ef4444';
}

new Chart(atsCanvas, {
  type: 'bar',
  data: {
    labels: scoredApps.map(a => a.company),
    datasets: [{
      data: scoredApps.map(a => a.ats_score),
      backgroundColor: scoredApps.map(a => atsColor(a.ats_score)),
      borderRadius: 4,
    }],
  },
  options: {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: ctx => `${ctx.parsed.x}% — ${scoredApps[ctx.dataIndex].position}`,
        },
      },
    },
    scales: {
      x: {
        min: 0, max: 100,
        ticks: { color: '#94a3b8', callback: v => v + '%' },
        grid: { color: '#334155' },
      },
      y: { ticks: { color: '#f1f5f9', font: { size: 12 } }, grid: { display: false } },
    },
  },
});

// ── Applications table ─────────────────────────────────────────────────────
const tbody = document.getElementById('appsBody');
const sorted = [...DATA.applications].sort((a, b) => b.created.localeCompare(a.created));

sorted.forEach(app => {
  const tr = document.createElement('tr');
  const companyCell = app.pr_url
    ? `<a href="${app.pr_url}" target="_blank">${app.company}</a>`
    : app.company;
  const scoreCell = app.ats_score !== null && app.ats_score !== undefined
    ? `<span class="${scoreClass(app.ats_score)}">${app.ats_score}%</span>`
    : '<span style="color:#475569">—</span>';
  const daysCell = app.days_since !== null && app.days_since !== undefined
    ? app.days_since + 'd'
    : '—';
  tr.innerHTML = `
    <td>${companyCell}</td>
    <td style="color:#94a3b8;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${app.position}">${app.position}</td>
    <td>${stageBadge(app.stage)}</td>
    <td>${scoreCell}</td>
    <td style="color:#94a3b8">${daysCell}</td>
    <td style="color:#94a3b8">${app.created || '—'}</td>
  `;
  tbody.appendChild(tr);
});
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(
        description="Generate Dashboard — Build a self-contained HTML dashboard of application stats. "
                    "Features: funnel doughnut chart, ATS scores bar chart, "
                    "applications per month bar chart, and active applications table."
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        dest="output_dir",
        default=str(REPO_ROOT / "docs"),
        help="Directory to write index.html into (default: docs/)",
    )
    parser.add_argument(
        "--no-gh",
        action="store_true",
        dest="no_gh",
        help="Skip GitHub CLI queries (faster, offline-safe)",
    )
    parser.add_argument(
        "--json-data",
        action="store_true",
        dest="json_data",
        help="Print collected data as JSON and exit (no HTML generated)",
    )
    parsed = parser.parse_args()
    output_dir = Path(parsed.output_dir)
    no_gh = parsed.no_gh
    json_data = parsed.json_data

    print("📊 Generating dashboard...")

    apps_dir = REPO_ROOT / "applications"
    if apps_dir.exists():
        count = sum(1 for d in apps_dir.iterdir() if d.is_dir() and (d / "meta.yml").exists())
        print(f"   Collecting data for {count} application(s)...")

    data = collect_data(no_gh=no_gh)

    if json_data:
        print(json.dumps(data, indent=2, default=str))
        return 0

    print(f"   Computing ATS scores...")

    # Serialize data to JS
    data_json = json.dumps(data, indent=2, default=str)

    # Inject into template
    html = HTML_TEMPLATE.replace("__DATA__", data_json)

    # Write output
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")

    size_kb = out_path.stat().st_size // 1024
    print(f"\n✅ Dashboard saved: {out_path}  ({size_kb} KB)")
    print(f"💡 Open with: open {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
