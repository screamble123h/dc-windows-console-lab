#!/usr/bin/env python3
"""Passive Windows console/focus observer: ISOLATED TEST VM ONLY.

Does NOT spawn PowerShell/CMD, close windows, or change settings.
Hard refuses FotoMag's production computer and non-Windows platforms.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

PRODUCTION_HOST = None  # public CI package omits internal hostnames

if sys.platform != 'win32':
    raise SystemExit('REFUSED: requires a separate interactive Windows lab VM; this OS is not Windows.')
if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
    raise SystemExit('REFUSED: this public observer is restricted to GitHub-hosted Windows CI.')
if os.environ.get('FOTOMAG_ISOLATED_WINDOWS_LAB', '') != 'YES':
    raise SystemExit('REFUSED: set FOTOMAG_ISOLATED_WINDOWS_LAB=YES only in an approved Windows lab VM.')

parser = argparse.ArgumentParser(description='Watch for newly visible console windows in isolated VM')
parser.add_argument('--seconds', type=int, default=120)
parser.add_argument('--interval', type=float, default=0.20)
parser.add_argument('--output', type=Path, default=None)
args = parser.parse_args()
if not (5 <= args.seconds <= 600 and 0.1 <= args.interval <= 2):
    parser.error('Allowed --seconds: 5..600, --interval: 0.1..2')

# No external console processes are needed. The optional psutil module provides cmdline.
try:
    import psutil
except ImportError:
    psutil = None

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
WindowCallback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WindowCallback, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
# Known console host classes. Class-based filtering avoids false positives from browser tab titles.
CONSOLE_CLASSES = {'ConsoleWindowClass', 'CASCADIA_HOSTING_WINDOW_CLASS', 'PseudoConsoleWindow'}

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('cntUsage', wintypes.DWORD),
        ('th32ProcessID', wintypes.DWORD),
        ('th32DefaultHeapID', ctypes.c_size_t),
        ('th32ModuleID', wintypes.DWORD),
        ('cntThreads', wintypes.DWORD),
        ('th32ParentProcessID', wintypes.DWORD),
        ('pcPriClassBase', wintypes.LONG),
        ('dwFlags', wintypes.DWORD),
        ('szExeFile', wintypes.WCHAR * 260),
    ]

def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='milliseconds')

def enumerate_console_windows() -> dict[int, dict]:
    out: dict[int, dict] = {}
    def cb(hwnd, unused):
        if not user32.IsWindowVisible(hwnd):
            return True
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, name, len(name))
        if name.value not in CONSOLE_CLASSES:
            return True
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, len(title))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = int(hwnd)
        out[h] = {'hwnd': h, 'class': name.value, 'title': title.value[:240], 'pid': pid.value}
        return True
    callback = WindowCallback(cb)
    if not user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return out

def process_metadata(pid: int) -> dict:
    result = {'pid': pid, 'ppid': None, 'process_name': None, 'command_line': None}
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot and snapshot != INVALID_HANDLE_VALUE:
        try:
            e = PROCESSENTRY32W()
            e.dwSize = ctypes.sizeof(e)
            ok = kernel32.Process32FirstW(snapshot, ctypes.byref(e))
            while ok:
                if e.th32ProcessID == pid:
                    result['ppid'] = int(e.th32ParentProcessID)
                    result['process_name'] = str(e.szExeFile)
                    break
                ok = kernel32.Process32NextW(snapshot, ctypes.byref(e))
        finally:
            kernel32.CloseHandle(snapshot)
    if psutil is not None:
        try:
            p = psutil.Process(pid)
            result['ppid'] = p.ppid()
            result['process_name'] = p.name()
            result['command_line'] = ' '.join(p.cmdline())[:700]
            result['started_at'] = datetime.fromtimestamp(p.create_time(), timezone.utc).isoformat()
        except (psutil.Error, OSError) as exc:
            result['cmdline_note'] = type(exc).__name__
    else:
        result['cmdline_note'] = 'unavailable_without_psutil (optional dependency, do not spawn shell)'
    return result

out_path = args.output or (Path(__file__).resolve().parent / f'lab_console_windows_{datetime.now():%Y%m%d_%H%M%S}.jsonl')
def log(event: str, **details) -> None:
    with out_path.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'time': iso_now(), 'event': event, **details}, ensure_ascii=False) + '\n')

baseline = enumerate_console_windows()
seen = baseline
prior_fg = int(user32.GetForegroundWindow() or 0)
log('lab_observer_start', host=os.environ.get('COMPUTERNAME'), seconds=args.seconds,
    baseline_window_count=len(baseline), baseline_hwnds=list(baseline),
    starting_foreground_hwnd=prior_fg, interactive_foreground_present=prior_fg != 0,
    psutil_available=psutil is not None)
start = time.monotonic()
ticks = 0
new_count = 0
focus_count = 0
try:
    while time.monotonic() - start < args.seconds:
        current = enumerate_console_windows()
        now_fg = int(user32.GetForegroundWindow() or 0)
        for hwnd, item in current.items():
            if hwnd not in seen:
                new_count += 1
                log('new_visible_console', **item, foreground=now_fg == hwnd,
                    process=process_metadata(item['pid']))
        for hwnd in seen.keys() - current.keys():
            log('console_window_disappeared', hwnd=hwnd)
        if now_fg != prior_fg and now_fg in current:
            focus_count += 1
            item = current[now_fg]
            log('foreground_entered_console', **item, process=process_metadata(item['pid']))
        seen = current
        prior_fg = now_fg
        ticks += 1
        time.sleep(args.interval)
finally:
    log('lab_observer_finished', ticks=ticks, new_visible_console_events=new_count,
        console_focus_events=focus_count, seconds=round(time.monotonic()-start, 2))
