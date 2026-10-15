"""Daily GitHub Actions utilization report, sent through the configured notifier.

Computes this month's workflow run count, total runtime and success rate
from the GitHub API. Sent once per day on the first run at/after
REPORT_HOUR_UTC. Requires GITHUB_TOKEN and GITHUB_REPOSITORY env vars
(provided automatically in GitHub Actions).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import requests

import notifier

log = logging.getLogger(__name__)

REPORT_HOUR_UTC = int(os.getenv("REPORT_HOUR_UTC", "1"))  # 01:00 UTC = 08:00 Thailand
FREE_TIER_MINUTES = 2000
MAX_PAGES = 40


def _fetch_month_runs(repo: str, token: str) -> list[dict]:
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
    url = f"https://api.github.com/repos/{repo}/actions/runs"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    params = {"created": f">={month_start}", "per_page": 100}
    runs: list[dict] = []
    for _ in range(MAX_PAGES):
        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        batch = r.json().get("workflow_runs", [])
        runs.extend(batch)
        next_link = r.links.get("next", {}).get("url")
        if not next_link:
            break
        url, params = next_link, None
    return runs


def _build_report(runs: list[dict]) -> str:
    total = len(runs)
    completed = [r for r in runs if r.get("status") == "completed"]
    success = sum(1 for r in completed if r.get("conclusion") == "success")
    failed = sum(1 for r in completed if r.get("conclusion") == "failure")

    minutes = 0.0
    for r in runs:
        try:
            start = datetime.fromisoformat(r["run_started_at"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
            minutes += max((end - start).total_seconds(), 0) / 60
        except (KeyError, ValueError, TypeError):
            continue

    month = datetime.now(timezone.utc).strftime("%B %Y")
    rate = (success / len(completed) * 100) if completed else 100.0
    return (
        f"🧾 <b>GitHub Actions report — {month}</b>\n"
        f"Runs this month: <b>{total}</b>\n"
        f"Success rate: <b>{rate:.1f}%</b> ({failed} failed)\n"
        f"Total runtime: <b>{minutes:.0f} min</b>\n"
        f"Free-tier note: public repo — minutes are <b>unlimited/free</b> "
        f"(private would use {minutes / FREE_TIER_MINUTES * 100:.1f}% of {FREE_TIER_MINUTES} min)"
    )


def maybe_send_daily_report(state: dict) -> None:
    token = os.getenv("GITHUB_TOKEN", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    if not token or not repo:
        return  # not running in GitHub Actions

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    if now.hour < REPORT_HOUR_UTC or state.get("last_usage_report") == today:
        return

    try:
        runs = _fetch_month_runs(repo, token)
    except requests.RequestException as e:
        log.warning("Usage report fetch failed: %s", e)
        return

    if notifier.send_text(_build_report(runs)):
        state["last_usage_report"] = today
        log.info("Daily usage report sent.")
