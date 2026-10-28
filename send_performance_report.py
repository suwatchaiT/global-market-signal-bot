"""Send an on-demand performance report using restored Actions state."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import journal
import notifier
import weekly_report

STATE_FILE = Path("state.json")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def send_report(state: dict) -> bool:
    messages = (
        journal.summary(state),
        journal.performance_table(state, 20),
        weekly_report.build_report(state),
    )
    return all(notifier.send_text(message) for message in messages)


if __name__ == "__main__":
    sys.exit(0 if send_report(load_state()) else 1)
