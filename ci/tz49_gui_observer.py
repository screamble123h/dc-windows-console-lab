#!/usr/bin/env python3
"""Passive HWND/focus telemetry for isolated Github-hosted Windows CI only.

Does not create or close Windows GUI objects. Because the runner is not a human
workstation, results CANNOT certify foreground-focus safety for FotoMag.
"""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

if not (sys.platform == 'win32' and os.getenv('GITHUB_ACTIONS') == 'true'
        and os.getenv('RUNNER_OS') == 'Windows' and os.getenv('RUNNER_ENVIRONMENT') == 'github-hosted'
        and os.getenv('FOTOMAG_ISOLATED_WINDOWS_LAB') == 'YES'):
    raise SystemExit('REFUSED_OUTSIDE_ISOLATED_GITHUB_WINDOWS_CI')
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--stop-file', type=Path, required=True)
parser.add_argument('--max-seconds', type=int, default=180)
parser.add_argument('--interval', type=float, default=.10)
a = parser.parse_args()
if not (5 <= a.max_seconds <= 360 and .05 <= a.interval <= 1):
    raise SystemExit('BAD_BOUNDS')

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [CALLBACK, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetForegroundWindow.restype = wintypes.HWND
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = [wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
kernel32.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.c_void_p]
kernel32.Process32FirstW.restype=wintypes.BOOL
kernel32.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.c_void_p]
kernel32.Process32NextW.restype=wintypes.BOOL
kernel32.CloseHandle.argtypes=[wintypes.HANDLE]
kernel32.CloseHandle.restype=wintypes.BOOL

class PROCESSENTRY32W(ctypes.Structure):
    _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),
              ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),
              ('cntThreads',wintypes.DWORD),('th32ParentProcessID',wintypes.DWORD),
              ('pcPriClassBase',wintypes.LONG),('dwFlags',wintypes.DWORD),
              ('szExeFile',wintypes.WCHAR*260)]
SHELL_NAMES={'conhost.exe','powershell.exe','pwsh.exe','cmd.exe','windowsterminal.exe','openconsole.exe'}
SHELL_CLASSES={'ConsoleWindowClass','CASCADIA_HOSTING_WINDOW_CLASS','PseudoConsoleWindow'}

def process_snapshot():
    allproc={}
    snap=kernel32.CreateToolhelp32Snapshot(2,0)
    if not snap or snap==ctypes.c_void_p(-1).value: return allproc
    try:
        pe=PROCESSENTRY32W();pe.dwSize=ctypes.sizeof(pe)
        valid=kernel32.Process32FirstW(snap,ctypes.byref(pe))
        while valid:
            allproc[int(pe.th32ProcessID)]={'pid':int(pe.th32ProcessID),
                'ppid':int(pe.th32ParentProcessID),'name':str(pe.szExeFile)}
            valid=kernel32.Process32NextW(snap,ctypes.byref(pe))
    finally:kernel32.CloseHandle(snap)
    return allproc

def windows():
    output={};fg=int(user32.GetForegroundWindow() or 0)
    def cb(hwnd,lparam):
        if not user32.IsWindowVisible(hwnd): return True
        buf=ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd,buf,256)
        cls=buf.value
        title=ctypes.create_unicode_buffer(400)
        user32.GetWindowTextW(hwnd,title,400)
        pid=wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        output[int(hwnd)]={'hwnd':int(hwnd),'pid':int(pid.value),'class':cls,
                           'title':title.value[:150], 'foreground':int(hwnd)==fg}
        return True
    if not user32.EnumWindows(CALLBACK(cb),0):
        raise ctypes.WinError(ctypes.get_last_error())
    return output,fg

def iso():return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

def emit(event,**v):
    with a.output.open('a',encoding='utf8') as f:f.write(json.dumps({'time_utc':iso(),'event':event,**v},ensure_ascii=False)+'\n')

a.output.parent.mkdir(parents=True,exist_ok=True)
start=time.monotonic();old,fg0=windows();fgprior=fg0
pids=process_snapshot();new_console=0;focus_events=0;cycles=0
emit('observer_start',foreground_hwnd=fg0,foreground_present=bool(fg0),
     existing_visible_windows=len(old),input_desktop_visibility='NOT_HUMAN_PROVEN',
     policy='CI_SESSION_OBSERVATION_ONLY')
try:
    while time.monotonic()-start<a.max_seconds and not a.stop_file.exists():
        curr,fg=windows()
        if fg!=fgprior:
            e=curr.get(fg)
            if e:
                p=process_snapshot().get(e['pid'],{})
                if e['class'] in SHELL_CLASSES or p.get('name','').lower() in SHELL_NAMES:
                    focus_events+=1
                    emit('console_foreground_transition',window=e,process=p)
        for hwnd,e in curr.items():
            if hwnd not in old:
                p=process_snapshot().get(e['pid'],{})
                if e['class'] in SHELL_CLASSES or p.get('name','').lower() in SHELL_NAMES:
                    new_console+=1
                    emit('new_visible_console_window',window=e,process=p)
        old,fgprior=curr,fg;cycles+=1
        if cycles%100==0: emit('heartbeat',cycles=cycles,console_new=new_console,focus_events=focus_events)
        time.sleep(a.interval)
except BaseException as err:
    emit('observer_error',message=type(err).__name__+':'+str(err)[:160])
    raise
finally:
    emit('observer_done',cycles=cycles,seconds=round(time.monotonic()-start,2),
         console_new=new_console,focus_events=focus_events,stopped_by_file=a.stop_file.exists(),
         overall_gui_verdict='NOT_PROVEN_NO_HUMAN_INTERACTIVE_DESKTOP')
