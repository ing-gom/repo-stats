"""Aggregate index.html generator for github-repo-stats data branch.

Run from the root of a checkout of the `github-repo-stats` branch. Reads each
tracked repo's ghrs-data/views_clones_aggregate.csv, fetches current stargazer
count via GitHub API, and writes index.html at cwd.
"""
import csv
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPOS = [
    "ing-gom/sts2-card-advisor",
    "ing-gom/sts2-combat-ai",
    "ing-gom/Sts2SkinManager",
    "ing-gom/sts2-game-speed",
    "ing-gom/sts2-undo-mod",
    "ing-gom/claude-mod-skills",
    "ing-gom/Sts2HostObserver",
    "ing-gom/Sts2MultiplayerSync",
    "ing-gom/Sts2SilkenTressBackport",
    "ing-gom/sts2-potion-drop-chance",
    "ing-gom/sts2-orb-layout",
]

TOKEN = os.environ.get("GH_TOKEN", "")


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


def main():
    items = []
    for repo in REPOS:
        agg = read_aggregate(repo) or {}
        meta = fetch_meta(repo)
        items.append({"repo": repo, **meta, **agg})

    items.sort(key=lambda x: x.get("recent_views", 0), reverse=True)

    def row(i):
        name = i["repo"].split("/")[-1]
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

    html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>ing-gom repository traffic</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 1200px; margin: 2em auto; padding: 0 1em; color: #1f2328; }}
  h1 {{ font-size: 1.5em; margin-bottom: 0.2em; }}
  .updated {{ color: #59636e; font-size: 0.9em; margin-bottom: 1.5em; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.92em; }}
  th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #d1d9e0; }}
  th {{ background: #f6f8fa; font-weight: 600; font-size: 0.85em; color: #59636e; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.desc {{ color: #59636e; font-size: 0.85em; max-width: 360px; }}
  a {{ color: #0969da; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .pending {{ color: #9a6700; font-size: 0.8em; }}
  footer {{ margin-top: 2em; color: #59636e; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>ing-gom repository traffic</h1>
<p class="updated">Updated {now} · 14d 윈도우는 GitHub API 의 최대 보존 기간 · total 은 수집 시작일 이후 누적</p>
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
{rows_html}
</tbody>
</table>
<footer>
  Powered by <a href="https://github.com/jgehrcke/github-repo-stats">jgehrcke/github-repo-stats</a> ·
  Source: <a href="https://github.com/ing-gom/repo-stats">ing-gom/repo-stats</a>
</footer>
</body>
</html>
"""
    Path("index.html").write_text(html, encoding="utf-8")
    print(f"Wrote index.html with {len(items)} repos")


if __name__ == "__main__":
    main()
