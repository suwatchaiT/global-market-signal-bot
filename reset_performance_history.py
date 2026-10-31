"""Reset signal-performance history without disturbing bot report state."""

import json
from pathlib import Path

STATE_FILE = Path("state.json")


def reset_state(state: dict) -> tuple[dict, int]:
    """Clear the journal and signal cooldowns, preserving scheduled-report state."""
    removed = len(state.get("signal_journal", []))
    cleaned = {
        key: value
        for key, value in state.items()
        if key != "signal_journal" and key.count("|") != 2
    }
    cleaned.pop("last_weekly_performance", None)
    cleaned["signal_journal"] = []
    return cleaned, removed


def main() -> None:
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    cleaned, removed = reset_state(state)
    STATE_FILE.write_text(json.dumps(cleaned, indent=2, sort_keys=True))
    print(f"Performance history reset: removed {removed} journal entries.")
    print("Technical signal scope remains XAUUSD and BTCUSD.")


if __name__ == "__main__":
    main()
