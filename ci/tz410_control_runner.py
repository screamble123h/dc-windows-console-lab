#!/usr/bin/env python3
"""Create controlled console-positive and hidden-console-negative observations.

NEVER USE ON A SHOP COMPUTER. Refuses to execute outside the specific public
GitHub-hosted Windows Actions repository. Does not use real data or credentials.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from tz410_control_analysis import read_jsonl, analyze_controls

EXPECTED_REPO = "screamble123h/dc-windows-console-lab"


def guard() -> None:
    allowed = (
        sys.platform == "win32"
        and os.getenv("GITHUB_ACTIONS") == "true"
        and os.getenv("RUNNER_ENVIRONMENT") == "github-hosted"
        and os.getenv("RUNNER_OS") == "Windows"
        and os.getenv("GITHUB_REPOSITORY") == EXPECTED_REPO
        and os.getenv("FOTOMAG_ISOLATED_WINDOWS_LAB") == "YES"
        and os.getenv("FOTOMAG_VM_EVIDENCE_SAFE") == "YES"
    )
    if not allowed:
        raise SystemExit("REFUSED_NOT_AUTHORIZED_INDEPENDENT_PUBLIC_WINDOWS_RUNNER")


def get_windows_api():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (CB, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    return user32, CB


def windows_for_pid(pid: int, user32, CB) -> list[int]:
    found = []

    def visit(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            found.append(int(hwnd))
        return True

    cb = CB(visit)
    if not user32.EnumWindows(cb, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return found


def find_named_window(marker: str, user32, CB) -> int | None:
    matches = []

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(350)
        user32.GetWindowTextW(hwnd, title, len(title))
        if marker in title.value:
            matches.append(int(hwnd))
        return True

    cb = CB(visit)
    if not user32.EnumWindows(cb, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return matches[0] if matches else None


def main() -> int:
    guard()
    root = Path.cwd()
    evidence = root / "evidence"
    evidence.mkdir(exist_ok=True)
    log = evidence / "TZ410_CONTROL_WINDOWS.jsonl"
    signal = evidence / "TZ410_OBSERVER_STOP.signal"
    for p in (log, signal):
        p.unlink(missing_ok=True)

    nonce = uuid.uuid4().hex[:12].upper()
    pos_marker = "TZ410_VISIBLE_POS_" + nonce
    neg_marker = "TZ410_HIDDEN_NEG_" + nonce
    env = os.environ.copy()
    user32, CB = get_windows_api()
    child = None
    notepad = None
    observer = None
    neg_exit = None
    notepad_in_foreground = False
    pos_pid = None
    notes = []
    obs_exit = None
    try:
        observer = subprocess.Popen(
            [sys.executable, "ci/tz49_gui_observer.py", "--output", str(log),
             "--stop-file", str(signal), "--max-seconds", "75", "--interval", "0.05"],
            cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for _ in range(80):
            if log.exists() and '"observer_start"' in log.read_text(encoding="utf-8", errors="replace"):
                break
            if observer.poll() is not None:
                notes.append("OBSERVER_EARLY_EXIT")
                break
            time.sleep(0.075)
        else:
            notes.append("OBSERVER_START_NOT_CONFIRMED")

        # Notepad is a non-production GUI fixture. Failure to foreground it on
        # session 0 is an expected limitation, never a focus-control PASS.
        try:
            notepad = subprocess.Popen(
                ["notepad.exe"], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            notepad_hwnd = None
            for _ in range(25):
                wins = windows_for_pid(notepad.pid, user32, CB)
                if wins:
                    notepad_hwnd = wins[0]
                    break
                time.sleep(0.12)
            if notepad_hwnd:
                user32.ShowWindow(notepad_hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(notepad_hwnd)
                time.sleep(0.25)
                notepad_in_foreground = int(user32.GetForegroundWindow() or 0) == notepad_hwnd
            else:
                notes.append("NOTEPAD_GUI_WINDOW_UNAVAILABLE")
        except Exception as exc:
            notes.append("NOTEPAD_FOCUS_ERROR_" + type(exc).__name__)

        # An *intentionally visible* console. If a runner cannot display it,
        # the control fails and no zero-window claim can be accepted.
        try:
            start = subprocess.STARTUPINFO()
            start.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            start.wShowWindow = subprocess.SW_SHOWNORMAL
            child = subprocess.Popen(
                ["cmd.exe", "/d", "/c", f"title {pos_marker} & ping -n 8 127.0.0.1 >NUL"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=start,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            pos_pid = child.pid
            positive_hwnd = None
            for _ in range(35):
                positive_hwnd = find_named_window(pos_marker, user32, CB)
                if positive_hwnd:
                    break
                time.sleep(0.1)
            if positive_hwnd and notepad_in_foreground:
                # Test whether foreground transfer is actually possible.
                # The passive observer must independently record the event.
                user32.SetForegroundWindow(positive_hwnd)
                time.sleep(0.28)
            time.sleep(1.1)
        except Exception as exc:
            notes.append("POSITIVE_SPAWN_ERROR_" + type(exc).__name__)
        finally:
            if child is not None:
                try:
                    if child.poll() is None:
                        child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=3)
                except OSError as exc:
                    notes.append("POSITIVE_CLEANUP_ERROR_" + type(exc).__name__)
                child = None

        # Negative control: a real cmd.exe whose console window must remain
        # suppressed, while the diagnostic marker is still unique.
        try:
            hidden = subprocess.run(
                ["cmd.exe", "/d", "/c",
                 f"title {neg_marker} & ping -n 4 127.0.0.1 >NUL"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=15, check=False,
            )
            neg_exit = hidden.returncode
            time.sleep(0.9)
        except Exception as exc:
            notes.append("NEGATIVE_SPAWN_ERROR_" + type(exc).__name__)
    finally:
        if notepad is not None:
            if notepad.poll() is None:
                notepad.terminate()
                try: notepad.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    notepad.kill()
                    notepad.wait(timeout=3)
        if observer is not None:
            signal.touch()
            try:
                _, stderr = observer.communicate(timeout=10)
                obs_exit = observer.returncode
                if stderr:
                    notes.append("OBSERVER_STDERR_" + stderr.decode("utf-8", "replace")[:250])
            except subprocess.TimeoutExpired:
                observer.kill()
                observer.communicate()
                obs_exit = 124
                notes.append("OBSERVER_TIMEOUT")

    events = read_jsonl(log)
    result = analyze_controls(events, pos_marker, neg_marker, pos_pid, neg_exit,
                              notepad_in_foreground)
    result.update({
        "test": "TZ410_VISIBLE_CONSOLE_CONTROL",
        "environment": "PUBLIC_GITHUB_HOSTED_WINDOWS_RUNNER_ONLY",
        "observer_exit_code": obs_exit,
        "observer_events": len(events),
        "notes": notes,
        "gui_user_session_certified": False,
        "not_ready_to_deploy": True,
    })
    (evidence / "TZ410_GUI_CONTROL_RESULTS.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"positive": result["positive"], "negative": result["negative"],
                      "focus": result["focus"], "calibrated_for_zero_window_claim": result["calibrated_for_zero_window_claim"],
                      "notes": notes}, ensure_ascii=False, indent=2), flush=True)
    # Not finding a positive window makes this runner unsuitable for GUI claims;
    # the final verdict step will block promotion even if the functional tests pass.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
