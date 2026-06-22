#!/usr/bin/env python3
# Generate aggregate language cards from public and authorized private repos.

from __future__ import annotations

import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

API_ROOT = "https://api.github.com"
OUTPUT_DIR = Path("dist")
TOP_LANGUAGES = 8

LANGUAGE_COLORS = {
    "TypeScript": "#3178C6", "JavaScript": "#F1E05A", "Python": "#3572A5",
    "Swift": "#F05138", "CSS": "#563D7C", "HTML": "#E34C26",
    "Shell": "#89E051", "Java": "#B07219", "Dart": "#00B4AB",
    "Kotlin": "#A97BFF", "C++": "#F34B7D", "C": "#555555",
    "C#": "#178600", "Vue": "#41B883", "SCSS": "#C6538C",
    "PHP": "#4F5D95", "Rust": "#DEA584", "Go": "#00ADD8",
    "Ruby": "#701516", "Objective-C": "#438EFF", "Jupyter Notebook": "#DA5B0B",
}

def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)

def request_json(url: str, token: str, retries: int = 3) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Sacha338-profile-language-card",
    }
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if error.code in {403, 429, 500, 502, 503, 504} and attempt < retries:
                time.sleep(attempt * 2)
                continue
            fail(f"GitHub API returned HTTP {error.code}: {body[:300]}")
        except urllib.error.URLError as error:
            if attempt < retries:
                time.sleep(attempt * 2)
                continue
            fail(f"Unable to reach GitHub API: {error}")
    fail(f"Unable to fetch {url}")

def owned_repositories(token: str, username: str) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({
            "per_page": 100, "page": page, "affiliation": "owner",
            "visibility": "all", "sort": "full_name",
        })
        batch = request_json(f"{API_ROOT}/user/repos?{query}", token)
        if not isinstance(batch, list):
            fail("Unexpected response while listing repositories.")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return [repo for repo in repos if repo.get("owner", {}).get("login", "").lower() == username.lower()]

def collect_languages(token: str, username: str, excluded_names: set[str]) -> tuple[Counter[str], int]:
    totals: Counter[str] = Counter()
    included_count = 0
    for repo in owned_repositories(token, username):
        name = str(repo.get("name", ""))
        full_name = str(repo.get("full_name", ""))
        if (
            not full_name or name in excluded_names or repo.get("fork")
            or repo.get("archived") or repo.get("disabled")
            or int(repo.get("size") or 0) == 0
        ):
            continue
        encoded = urllib.parse.quote(full_name, safe="/")
        data = request_json(f"{API_ROOT}/repos/{encoded}/languages", token)
        if not isinstance(data, dict):
            continue
        repo_total = 0
        for language, byte_count in data.items():
            if isinstance(byte_count, int) and byte_count > 0:
                totals[str(language)] += byte_count
                repo_total += byte_count
        if repo_total > 0:
            included_count += 1
    return totals, included_count

def fmt_bytes(value: int) -> str:
    amount = float(value)
    for unit in ["B", "KB", "MB", "GB"]:
        if amount < 1024 or unit == "GB":
            return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"

def render_card(languages: list[tuple[str, int, float]], repo_count: int, total_bytes: int, dark: bool) -> str:
    width, row_height, top = 720, 34, 104
    height = top + len(languages) * row_height + 52
    background = "#0D1117" if dark else "#FFFFFF"
    border = "#30363D" if dark else "#D0D7DE"
    title = "#FFFFFF" if dark else "#24292F"
    text = "#C9D1D9" if dark else "#24292F"
    muted = "#8B949E" if dark else "#57606A"
    track = "#21262D" if dark else "#EAEFF5"
    accent = "#7C9CFF" if dark else "#2B4BEE"

    rows = []
    for index, (language, byte_count, percent) in enumerate(languages):
        y = top + index * row_height
        color = LANGUAGE_COLORS.get(language, "#8B949E")
        label = html.escape(language)
        bar_width = max(4.0, 390.0 * percent / 100.0)
        rows.append(f'''
    <circle cx="35" cy="{y - 4}" r="5" fill="{color}"/>
    <text x="51" y="{y}" class="language">{label}</text>
    <text x="675" y="{y}" text-anchor="end" class="percentage">{percent:.1f}%</text>
    <rect x="230" y="{y - 12}" width="390" height="9" rx="4.5" fill="{track}"/>
    <rect x="230" y="{y - 12}" width="{bar_width:.1f}" height="9" rx="4.5" fill="{color}">
      <animate attributeName="width" from="0" to="{bar_width:.1f}" dur="0.9s" begin="{index * 0.08:.2f}s" fill="freeze"/>
    </rect>''')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Codebase languages</title>
  <desc id="desc">Aggregated language usage from owned public and authorized private GitHub repositories.</desc>
  <style>
    .heading{{fill:{title};font:700 22px Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
    .meta{{fill:{muted};font:500 12px Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
    .language{{fill:{text};font:600 13px Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
    .percentage{{fill:{text};font:700 12px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}}
    .badge{{fill:{accent};font:700 11px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;letter-spacing:.8px}}
  </style>
  <defs>
    <linearGradient id="accent-line" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{accent}"/><stop offset="1" stop-color="#A855F7"/></linearGradient>
    <filter id="glow" x="-30%" y="-200%" width="160%" height="500%"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="18" fill="{background}" stroke="{border}"/>
  <rect x="24" y="24" width="5" height="38" rx="2.5" fill="url(#accent-line)" filter="url(#glow)"/>
  <text x="44" y="43" class="heading">Codebase languages</text>
  <text x="44" y="62" class="meta">Public + authorized private repositories</text>
  <rect x="522" y="29" width="154" height="26" rx="13" fill="{accent}" opacity=".13"/>
  <text x="599" y="46" text-anchor="middle" class="badge">PRIVATE INCLUDED</text>
  <text x="24" y="87" class="meta">{repo_count} repositories • {fmt_bytes(total_bytes)} classified by GitHub Linguist</text>
  {''.join(rows)}
  <text x="24" y="{height - 20}" class="meta">Updated automatically • Aggregate totals only • Private repository names are never displayed</text>
</svg>
'''

def main() -> None:
    token = os.getenv("PROFILE_STATS_TOKEN", "").strip()
    username = os.getenv("GITHUB_USERNAME", "").strip()
    if not token:
        fail("PROFILE_STATS_TOKEN is missing.")
    if not username:
        fail("GITHUB_USERNAME is missing.")
    excluded = {name.strip() for name in os.getenv("EXCLUDE_REPOS", "").split(",") if name.strip()}
    totals, repo_count = collect_languages(token, username, excluded)
    if not totals:
        fail("No language data returned. Check the token's repository access.")
    total_bytes = sum(totals.values())
    languages = [(name, count, count / total_bytes * 100) for name, count in totals.most_common(TOP_LANGUAGES)]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "languages.svg").write_text(render_card(languages, repo_count, total_bytes, False), encoding="utf-8")
    (OUTPUT_DIR / "languages-dark.svg").write_text(render_card(languages, repo_count, total_bytes, True), encoding="utf-8")
    print(f"Generated language cards from {repo_count} repositories.")
    for name, count, percent in languages:
        print(f"- {name}: {percent:.2f}% ({fmt_bytes(count)})")

if __name__ == "__main__":
    main()
