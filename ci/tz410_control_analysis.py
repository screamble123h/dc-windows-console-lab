"""Pure evidence analysis for FotoMag TZ4.10; no Windows APIs or processes.

A zero-window result is not valid evidence unless the same observer first
recognizes a deliberately visible, uniquely named console in that session.
This module never claims human-interactive GUI proof for GitHub-hosted runners.
"""
from __future__ import annotations

import json
from pathlib import Path

CONSOLE_CLASSES = {
    "ConsoleWindowClass",
    "CASCADIA_HOSTING_WINDOW_CLASS",
    "PseudoConsoleWindow",
}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            events.append({"event": "unparseable_observer_line"})
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def console_event_match(event: dict, marker: str) -> bool:
    if event.get("event") != "new_visible_console_window":
        return False
    window = event.get("window") or {}
    process = event.get("process") or {}
    if not isinstance(window, dict) or not isinstance(process, dict):
        return False
    title = str(window.get("title", ""))
    p_name = str(process.get("name", "")).lower()
    is_console = window.get("class") in CONSOLE_CLASSES or p_name in {
        "cmd.exe", "powershell.exe", "conhost.exe", "pwsh.exe", "openconsole.exe"
    }
    return is_console and marker in title and int(window.get("hwnd") or 0) > 0 and int(window.get("pid") or 0) > 0


def analyze_controls(events: list[dict], pos_marker: str, neg_marker: str,
                     positive_spawned_pid: int | None, negative_exit: int | None,
                     notepad_foreground_confirmed: bool) -> dict:
    started = any(e.get("event") == "observer_start" for e in events)
    finished = any(e.get("event") == "observer_done" for e in events)
    exceptions = [e for e in events if e.get("event") in ("observer_error", "unparseable_observer_line")]
    positive = [e for e in events if console_event_match(e, pos_marker)]
    negative = [e for e in events if console_event_match(e, neg_marker)]
    focus_positive = [e for e in events
                      if e.get("event") == "console_foreground_transition"
                      and pos_marker in str((e.get("window") or {}).get("title", ""))]
    p = positive[0] if positive else None
    w = p.get("window", {}) if p else {}
    process = p.get("process", {}) if p else {}
    owner_pid = int(w.get("pid") or 0)
    owner_ppid = int(process.get("ppid") or 0)
    direct_pid_match = bool(positive_spawned_pid and owner_pid == positive_spawned_pid)
    child_pid_match = bool(positive_spawned_pid and owner_ppid == positive_spawned_pid)
    # conhost.exe is often the HWND owner rather than cmd.exe. An exact title
    # nonce supports correlation but does not by itself prove parentage.
    title_correlates = bool(p and pos_marker in str(w.get("title", "")))
    valid_events = started and finished and not exceptions
    return {
        "observer_started": started,
        "observer_finished": finished,
        "observer_errors": exceptions,
        "positive": {
            "status": "PASS" if valid_events and positive and title_correlates else "NOT_DETECTED",
            "spawned_pid": positive_spawned_pid,
            "detected": bool(positive),
            "timestamp_utc": p.get("time_utc") if p else None,
            "hwnd": w.get("hwnd"),
            "window_owner_pid": owner_pid or None,
            "window_owner_parent_pid": owner_ppid or None,
            "window_owner_name": process.get("name"),
            "window_class": w.get("class"),
            "window_title_nonce_matched": title_correlates,
            "is_window_visible": True if positive else None,
            "direct_pid_match": direct_pid_match,
            "child_pid_match": child_pid_match,
            "relationship_note": "console HWND can belong to conhost.exe; title nonce is supplementary evidence, not process ancestry",
        },
        "negative": {
            "status": "PASS" if valid_events and negative_exit == 0 and not negative else "FAIL_OR_INCONCLUSIVE",
            "exit_code": negative_exit,
            "matched_visible_windows": len(negative),
        },
        "focus": {
            "status": "PASS" if valid_events and notepad_foreground_confirmed and bool(focus_positive)
                      else "NOT_PROVEN",
            "notepad_foreground_confirmed": bool(notepad_foreground_confirmed),
            "positive_console_foreground_transitions": len(focus_positive),
            "human_workstation_focus_certified": False,
        },
        "calibrated_for_zero_window_claim": bool(valid_events and positive and not negative and negative_exit == 0),
        "github_runner_is_human_interactive_desktop": "NOT_PROVEN",
    }
