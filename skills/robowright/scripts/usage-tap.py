#!/usr/bin/env python3
"""
usage-tap.py — the status line, and the only source of plan usage outside the desktop app.

Claude Code runs this as `statusLine.command` with the session's JSON on stdin
(https://code.claude.com/docs/en/statusline.md). Its `rate_limits` carries the account's 5-hour
and 7-day usage as of the session's last API response. The tap records that to
$CLAUDE_USAGE_DIR/latest.json (default ~/.claude/usage) for `claude-usage` and `usage-guard`,
then prints one line: model · context · 5h · 7d.

It writes only when this session has had an API response since its last write
(`cost.total_api_duration_ms` moved). Claude Code also re-runs the status line with no API call —
a permission-mode change, a window reaching `resets_at` — and re-stamping those would pass old
numbers off as fresh. No `rate_limits`, no write: the previous reading stands.

Always exits 0 and never writes to stderr: a failing status line goes blank.
"""

import json
import os
import sys
import time

WINDOWS = (("five_hour", "5h"), ("seven_day", "7d"))


def usage_dir():
    return os.path.expanduser(os.environ.get("CLAUDE_USAGE_DIR") or "~/.claude/usage")


def windows_of(data):
    limits = data.get("rate_limits")
    if not isinstance(limits, dict):
        return {}
    found = {}
    for key, _ in WINDOWS:
        window = limits.get(key)
        if not isinstance(window, dict):
            continue
        pct = window.get("used_percentage")
        if isinstance(pct, (int, float)) and not isinstance(pct, bool):
            found[key] = {"used_percentage": pct, "resets_at": window.get("resets_at")}
    return found


def write_atomically(path, text):
    temp = f"{path}.{os.getpid()}.tmp"
    with open(temp, "w") as f:
        f.write(text)
    os.replace(temp, path)


def record(data, windows):
    session_id = str(data.get("session_id") or "unknown")
    api_ms = (data.get("cost") or {}).get("total_api_duration_ms")
    root = usage_dir()
    marks = os.path.join(root, "sessions")
    os.makedirs(marks, exist_ok=True)
    mark = os.path.join(marks, session_id.replace("/", "_"))
    try:
        with open(mark) as f:
            last_api_ms = f.read().strip()
    except OSError:
        last_api_ms = None
    if api_ms is not None and last_api_ms == str(api_ms):
        return
    reading = {"captured_at": int(time.time()), "session_id": session_id, **windows}
    write_atomically(os.path.join(root, "latest.json"), json.dumps(reading) + "\n")
    write_atomically(mark, f"{api_ms}\n")


def percent(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.0f}%"
    return "--"


def line(data, windows):
    model = (data.get("model") or {}).get("display_name") or "claude"
    context = percent((data.get("context_window") or {}).get("used_percentage"))
    parts = [model, f"ctx {context}"]
    for key, label in WINDOWS:
        parts.append(f"{label} {percent(windows.get(key, {}).get('used_percentage'))}")
    return " · ".join(parts)


def main():
    try:
        data = json.loads(sys.stdin.read())
        if not isinstance(data, dict):
            raise ValueError("status line input is not an object")
    except Exception:
        print("claude")
        return
    windows = windows_of(data)
    if windows:
        try:
            record(data, windows)
        except Exception:
            pass
    print(line(data, windows))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("claude")
    sys.exit(0)
