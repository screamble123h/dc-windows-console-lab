#!/usr/bin/env python3
"""Classify runner's Windows window station and session. Does not spawn applications.

This is only a *candidate* GUI probe, never proof of human-observable focus.
Refuses all non-GitHub-hosted Windows environments to avoid production use.
"""
import ctypes
import json
import os
import platform
from ctypes import wintypes
from pathlib import Path


def main():
    out = Path('evidence/runner_session_probe.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    assert os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'GitHub-hosted runner only'
    assert os.environ.get('RUNNER_OS') == 'Windows' and os.name == 'nt', 'Windows only'
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    u32 = ctypes.WinDLL('user32', use_last_error=True)
    k32.GetCurrentProcessId.restype = wintypes.DWORD
    k32.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD
    k32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    k32.ProcessIdToSessionId.restype = wintypes.BOOL
    u32.GetProcessWindowStation.restype = wintypes.HANDLE
    u32.GetForegroundWindow.restype = wintypes.HWND
    u32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    u32.OpenInputDesktop.restype = wintypes.HANDLE
    u32.CloseDesktop.argtypes = [wintypes.HANDLE]
    u32.CloseDesktop.restype = wintypes.BOOL
    u32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, wintypes.INT,
                                             wintypes.LPVOID, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.DWORD)]
    u32.GetUserObjectInformationW.restype = wintypes.BOOL

    pid = k32.GetCurrentProcessId()
    sid = wintypes.DWORD()
    sid_ok = bool(k32.ProcessIdToSessionId(pid, ctypes.byref(sid)))
    active_sid = k32.WTSGetActiveConsoleSessionId()
    fg = int(u32.GetForegroundWindow() or 0)

    def obj_name(handle):
        if not handle: return None
        buff = ctypes.create_unicode_buffer(256)
        size = wintypes.DWORD()
        ok = u32.GetUserObjectInformationW(handle, 2, ctypes.byref(buff), ctypes.sizeof(buff), ctypes.byref(size))
        return buff.value if ok else None

    winsta = obj_name(u32.GetProcessWindowStation())
    input_desktop = u32.OpenInputDesktop(0, False, 0x0001)
    desktop = obj_name(input_desktop) if input_desktop else None
    if input_desktop: u32.CloseDesktop(input_desktop)
    candidate = bool(sid_ok and sid.value != 0 and sid.value == active_sid and
                     winsta and winsta.lower() == 'winsta0' and desktop and fg != 0)
    payload = {'platform': platform.platform(), 'windows': True,
               'process_session_id': sid.value if sid_ok else None,
               'active_console_session_id': active_sid,
               'window_station': winsta, 'input_desktop': desktop,
               'foreground_hwnd_present': fg != 0,
               'interactive_candidate': candidate,
               'real_human_visible_desktop_proven': False,
               'conclusion': 'GUI_FOCUS_NOT_PROVEN_ON_HOSTED_RUNNER'}
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
