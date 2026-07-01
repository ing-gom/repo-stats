"""Aggregate index.html generator for github-repo-stats data branch.

Run from the root of a checkout of the `github-repo-stats` branch. Reads each
tracked repo's ghrs-data/views_clones_aggregate.csv, fetches current stargazer
count via GitHub API, and writes index.html with interactive charts (Chart.js).
"""
import csv
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOKEN = os.environ.get("GH_TOKEN", "")


def get_repos():
    """Repo list, in priority order:

    1. REPOS_JSON env (JSON array) — passed from the workflow's `discover` job,
       so newly-public repos are picked up without editing this file.
    2. Fallback: whatever repos already have data on the checked-out data branch
       (``<owner>/<repo>/ghrs-data/views_clones_aggregate.csv``).
    """
    env = os.environ.get("REPOS_JSON", "").strip()
    if env:
        try:
            repos = json.loads(env)
            if repos:
                return repos
        except json.JSONDecodeError as e:
            print(f"[warn] REPOS_JSON parse failed, falling back to data dirs: {e}")
    found = sorted(
        f"{p.parts[0]}/{p.parts[1]}"
        for p in Path(".").glob("*/*/ghrs-data/views_clones_aggregate.csv")
    )
    return found


def color_for(idx: int) -> str:
    """Distinct 6-digit hex per repo via golden-angle hue rotation.

    Kept as hex (not hsl()) because the front-end appends 'cc' for the stacked
    fill alpha, which only works on hex.
    """
    hue = (idx * 137.508) % 360.0
    return _hsl_to_hex(hue, 0.62, 0.46)


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = l - c / 2
    r, g, b = {
        0: (c, x, 0), 1: (x, c, 0), 2: (0, c, x),
        3: (0, x, c), 4: (x, 0, c), 5: (c, 0, x),
    }[int(h // 60) % 6]
    return "#{:02x}{:02x}{:02x}".format(
        round((r + m) * 255), round((g + m) * 255), round((b + m) * 255)
    )


def fetch_meta(repo: str):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}",
        headers={
            "Authorization": f"token {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "repo-stats-index",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            return {
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "desc": data.get("description") or "",
            }
    except Exception as e:
        print(f"[warn] meta fetch failed for {repo}: {e}")
        return {"stars": 0, "forks": 0, "desc": ""}


def read_aggregate(repo: str):
    path = Path(repo) / "ghrs-data" / "views_clones_aggregate.csv"
    if not path.exists():
        return None
    with path.open() as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    daily = [
        {
            "date": r["time_iso8601"][:10],
            "views_total": int(r["views_total"]),
            "clones_total": int(r["clones_total"]),
            "views_unique": int(r["views_unique"]),
            "clones_unique": int(r["clones_unique"]),
        }
        for r in rows
    ]
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    tv = tc = rv = rc = uv = uc = 0
    for r in rows:
        ts = datetime.fromisoformat(r["time_iso8601"])
        v = int(r["views_total"])
        c = int(r["clones_total"])
        vu = int(r["views_unique"])
        cu = int(r["clones_unique"])
        tv += v
        tc += c
        if ts >= cutoff:
            rv += v
            rc += c
            uv += vu
            uc += cu
    return {
        "daily": daily,
        "total_views": tv,
        "total_clones": tc,
        "recent_views": rv,
        "recent_clones": rc,
        "recent_unique_views": uv,
        "recent_unique_clones": uc,
        "first_date": rows[0]["time_iso8601"][:10],
        "last_date": rows[-1]["time_iso8601"][:10],
        "days": len(rows),
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>ing-gom repository traffic</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 1200px; margin: 2em auto; padding: 0 1em; color: #1f2328; }
  h1 { font-size: 1.5em; margin-bottom: 0.2em; }
  h2 { font-size: 1.05em; margin: 2em 0 0.6em; color: #1f2328; }
  .updated { color: #59636e; font-size: 0.9em; margin-bottom: 1.5em; }
  .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
             gap: 12px; margin-bottom: 1.6em; }
  .card { padding: 12px 14px; border: 1px solid #d1d9e0; border-radius: 6px; background: #ffffff; }
  .card .label { color: #59636e; font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.04em; }
  .card .value { font-size: 1.5em; font-weight: 600; margin-top: 4px; font-variant-numeric: tabular-nums; }
  .controls { display: flex; gap: 16px; align-items: center; margin-bottom: 0.6em;
              font-size: 0.9em; flex-wrap: wrap; }
  .controls label { color: #59636e; }
  .controls select { padding: 4px 8px; border: 1px solid #d1d9e0; border-radius: 4px; background: #ffffff; }
  .controls button { padding: 4px 10px; border: 1px solid #d1d9e0; border-radius: 4px;
                     background: #ffffff; cursor: pointer; font: inherit; color: inherit; }
  .controls button.active { background: #ddf4ff; border-color: #0969da; }
  .chart-wrap { position: relative; height: 360px; margin-bottom: 1em; }
  .chart-wrap.bar { height: 420px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.92em; }
  th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #d1d9e0; }
  th { background: #f6f8fa; font-weight: 600; font-size: 0.85em; color: #59636e; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  td.desc { color: #59636e; font-size: 0.85em; max-width: 360px; }
  a { color: #0969da; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .pending { color: #9a6700; font-size: 0.8em; }
  footer { margin-top: 2em; color: #59636e; font-size: 0.85em; }
</style>
</head>
<body>
<h1>ing-gom repository traffic</h1>
<p class="updated">Updated __NOW__ · 14d 윈도우는 GitHub API 최대 보존 기간 · total 은 수집 시작일 이후 누적</p>

<div class="summary">
  <div class="card"><div class="label">Repos</div><div class="value">__NUM_REPOS__</div></div>
  <div class="card"><div class="label">Views (14d)</div><div class="value">__RECENT_VIEWS__</div></div>
  <div class="card"><div class="label">Clones (14d)</div><div class="value">__RECENT_CLONES__</div></div>
  <div class="card"><div class="label">Views (total)</div><div class="value">__TOTAL_VIEWS__</div></div>
  <div class="card"><div class="label">Clones (total)</div><div class="value">__TOTAL_CLONES__</div></div>
  <div class="card"><div class="label">★ Total</div><div class="value">__TOTAL_STARS__</div></div>
</div>

<h2>Daily trend</h2>
<div class="controls">
  <label>Metric
    <select id="trendMetric">
      <option value="views_total">Views (total)</option>
      <option value="views_unique">Views (unique)</option>
      <option value="clones_total">Clones (total)</option>
      <option value="clones_unique">Clones (unique)</option>
    </select>
  </label>
  <button id="toggleSmooth" type="button">7-day rolling avg</button>
  <button id="toggleStack" type="button">Stacked</button>
</div>
<div class="chart-wrap"><canvas id="trendChart"></canvas></div>

<h2>Repo totals</h2>
<div class="controls">
  <label>Sort by
    <select id="totalMetric">
      <option value="recent_views">Views (14d)</option>
      <option value="recent_unique_views">Unique views (14d)</option>
      <option value="recent_clones">Clones (14d)</option>
      <option value="total_views">Views (total)</option>
      <option value="total_clones">Clones (total)</option>
      <option value="stars">★ Stars</option>
    </select>
  </label>
</div>
<div class="chart-wrap bar"><canvas id="totalsChart"></canvas></div>

<h2>Detail</h2>
<table>
<thead>
<tr>
  <th>Repository</th>
  <th>Views (14d)</th>
  <th>Unique (14d)</th>
  <th>Clones (14d)</th>
  <th>Views (total)</th>
  <th>Clones (total)</th>
  <th>★</th>
  <th>Description</th>
</tr>
</thead>
<tbody>
__ROWS__
</tbody>
</table>

<footer>
  Powered by <a href="https://github.com/jgehrcke/github-repo-stats">jgehrcke/github-repo-stats</a> ·
  Source: <a href="https://github.com/ing-gom/repo-stats">ing-gom/repo-stats</a>
</footer>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<script id="repo-data" type="application/json">__CHART_JSON__</script>
<script>
const REPO_DATA = JSON.parse(document.getElementById('repo-data').textContent);
const allDates = [...new Set(REPO_DATA.flatMap(r => (r.daily || []).map(d => d.date)))].sort();

function rolling(values, window) {
  const out = [];
  for (let i = 0; i < values.length; i++) {
    let sum = 0, n = 0;
    for (let j = Math.max(0, i - window + 1); j <= i; j++) {
      if (values[j] != null) { sum += values[j]; n++; }
    }
    out.push(n ? sum / n : 0);
  }
  return out;
}

let trendChart, totalsChart;
let smoothMode = false;
let stackMode = false;

function buildTrendDatasets(metric) {
  return REPO_DATA.map(r => {
    const byDate = Object.fromEntries((r.daily || []).map(d => [d.date, d[metric]]));
    let series = allDates.map(d => byDate[d] ?? 0);
    if (smoothMode) series = rolling(series, 7);
    return {
      label: r.name,
      data: series,
      borderColor: r.color,
      backgroundColor: stackMode ? r.color + 'cc' : r.color,
      tension: 0.25,
      borderWidth: 1.5,
      pointRadius: 0,
      pointHoverRadius: 3,
      fill: stackMode,
    };
  });
}

function renderTrend() {
  const metric = document.getElementById('trendMetric').value;
  if (trendChart) trendChart.destroy();
  trendChart = new Chart(document.getElementById('trendChart'), {
    type: 'line',
    data: { labels: allDates, datasets: buildTrendDatasets(metric) },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          type: 'time',
          time: { unit: 'day', tooltipFormat: 'yyyy-MM-dd' },
          ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
        },
        y: {
          beginAtZero: true,
          stacked: stackMode,
          ticks: { precision: 0 },
        },
      },
      plugins: {
        legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8, font: { size: 11 } } },
      },
    },
  });
}

function renderTotals() {
  const metric = document.getElementById('totalMetric').value;
  if (totalsChart) totalsChart.destroy();
  const sorted = [...REPO_DATA].sort((a, b) => (b[metric] ?? 0) - (a[metric] ?? 0));
  totalsChart = new Chart(document.getElementById('totalsChart'), {
    type: 'bar',
    data: {
      labels: sorted.map(r => r.name),
      datasets: [{
        label: metric,
        data: sorted.map(r => r[metric] ?? 0),
        backgroundColor: sorted.map(r => r.color),
        borderRadius: 3,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
      plugins: { legend: { display: false } },
    },
  });
}

document.getElementById('trendMetric').addEventListener('change', renderTrend);
document.getElementById('totalMetric').addEventListener('change', renderTotals);
document.getElementById('toggleSmooth').addEventListener('click', e => {
  smoothMode = !smoothMode;
  e.currentTarget.classList.toggle('active', smoothMode);
  renderTrend();
});
document.getElementById('toggleStack').addEventListener('click', e => {
  stackMode = !stackMode;
  e.currentTarget.classList.toggle('active', stackMode);
  renderTrend();
});

renderTrend();
renderTotals();
</script>
</body>
</html>
"""


def main():
    repos = get_repos()
    items = []
    for idx, repo in enumerate(repos):
        agg = read_aggregate(repo) or {}
        meta = fetch_meta(repo)
        items.append({
            "repo": repo,
            "name": repo.split("/")[-1],
            "color": color_for(idx),
            **meta,
            **agg,
        })

    items.sort(key=lambda x: x.get("recent_views", 0), reverse=True)

    chart_data = [
        {
            "repo": i["repo"],
            "name": i["name"],
            "color": i["color"],
            "daily": i.get("daily", []),
            "stars": i.get("stars", 0),
            "forks": i.get("forks", 0),
            "recent_views": i.get("recent_views", 0),
            "recent_unique_views": i.get("recent_unique_views", 0),
            "recent_clones": i.get("recent_clones", 0),
            "recent_unique_clones": i.get("recent_unique_clones", 0),
            "total_views": i.get("total_views", 0),
            "total_clones": i.get("total_clones", 0),
        }
        for i in items
    ]
    chart_json = json.dumps(chart_data, ensure_ascii=False)

    total_views_all = sum(i.get("total_views", 0) for i in items)
    total_clones_all = sum(i.get("total_clones", 0) for i in items)
    recent_views_all = sum(i.get("recent_views", 0) for i in items)
    recent_clones_all = sum(i.get("recent_clones", 0) for i in items)
    total_stars = sum(i.get("stars", 0) for i in items)
    num_repos = sum(1 for i in items if i.get("daily"))

    def row(i):
        name = i["name"]
        has_report = "total_views" in i
        link = (
            f"<a href='{i['repo']}/latest-report/report.html'>{name}</a>"
            if has_report
            else f"{name} <span class='pending'>(데이터 수집 대기)</span>"
        )
        return (
            "<tr>"
            f"<td>{link}</td>"
            f"<td class='num'>{i.get('recent_views', '–')}</td>"
            f"<td class='num'>{i.get('recent_unique_views', '–')}</td>"
            f"<td class='num'>{i.get('recent_clones', '–')}</td>"
            f"<td class='num'>{i.get('total_views', '–')}</td>"
            f"<td class='num'>{i.get('total_clones', '–')}</td>"
            f"<td class='num'>{i.get('stars', 0)}</td>"
            f"<td class='desc'>{i.get('desc', '')}</td>"
            "</tr>"
        )

    rows_html = "\n".join(row(i) for i in items)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = (HTML_TEMPLATE
            .replace("__NOW__", now)
            .replace("__NUM_REPOS__", str(num_repos))
            .replace("__RECENT_VIEWS__", f"{recent_views_all:,}")
            .replace("__RECENT_CLONES__", f"{recent_clones_all:,}")
            .replace("__TOTAL_VIEWS__", f"{total_views_all:,}")
            .replace("__TOTAL_CLONES__", f"{total_clones_all:,}")
            .replace("__TOTAL_STARS__", str(total_stars))
            .replace("__ROWS__", rows_html)
            .replace("__CHART_JSON__", chart_json))

    Path("index.html").write_text(html, encoding="utf-8")
    print(f"Wrote index.html with {len(items)} repos")


if __name__ == "__main__":
    main()
